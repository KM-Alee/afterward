"""Store a new message; approved replies go through the engine's reply pipeline.

`ingest_message` only matches and stores. `process_inbound` is the async path the
poll job uses: unapproved or unsorted mail is stored and held, approved replies
run through `app.engine.pipeline.process_reply`. A missing AI client fails loudly.
Model output is never copied into approved recipients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import EventBus, MailMessage
from app.engine.outcome import CommitmentView, FactView, PlanView, conditions_from, outcome_check
from app.engine.pipeline import process_reply
from app.mail.errors import MailError
from app.mail.match import list_unsorted, match_message
from app.mail.parse import extract_text
from app.models import (
    Account,
    Case,
    Commitment,
    Message,
    MessageDirection,
    OutcomeCheck,
    Plan,
    PlanStatus,
    ProviderProfile,
    RecipientCheck,
)

ExtractionState = Literal["called", "skipped"]


@dataclass
class UnsortedItem:
    """A message that could not be stored on a case."""

    mailbox: str
    gmail_id: str
    from_addr: str
    subject: str
    received_at: datetime
    reason: str


@dataclass
class UnsortedTray:
    """In-process tray for mail that has no case row to hang from."""

    items: list[UnsortedItem] = field(default_factory=list)

    def add(self, message: MailMessage, reason: str) -> None:
        self.items.append(
            UnsortedItem(
                mailbox=message.mailbox,
                gmail_id=message.gmail_id,
                from_addr=message.from_addr,
                subject=message.subject,
                received_at=message.received_at,
                reason=reason,
            )
        )


@dataclass(frozen=True)
class IngestResult:
    """What the inbound glue did with one polled message."""

    gmail_id: str
    case_id: UUID | None
    account_id: UUID | None
    recipient_check: str | None
    method: str
    unsorted: bool
    message_id: UUID | None
    extraction: ExtractionState
    new: bool = False


def ingest_messages(
    session: Session,
    messages: list[MailMessage],
    *,
    bus: EventBus | None = None,
    bound_case_id: UUID | None = None,
    tray: UnsortedTray | None = None,
) -> list[IngestResult]:
    """Match and store. Extraction is `process_inbound`'s job. Recipients stay put."""
    holding = tray if tray is not None else UnsortedTray()
    return [
        ingest_message(
            session,
            message,
            bus=bus,
            bound_case_id=bound_case_id,
            tray=holding,
        )
        for message in messages
    ]


def ingest_message(
    session: Session,
    message: MailMessage,
    *,
    bus: EventBus | None = None,
    bound_case_id: UUID | None = None,
    tray: UnsortedTray | None = None,
) -> IngestResult:
    """Ingest one message. A duplicate Gmail id is not extracted twice."""
    extracted = extract_text(message.full_text or message.latest_text)
    matched = match_message(session, message, bound_case_id=bound_case_id)
    if matched.case_id is None:
        if tray is not None:
            tray.add(message, "no_case")
        return IngestResult(
            gmail_id=message.gmail_id,
            case_id=None,
            account_id=None,
            recipient_check=matched.recipient_check.value,
            method=matched.method,
            unsorted=True,
            message_id=None,
            extraction="skipped",
        )
    existing = session.scalar(
        select(Message).where(
            Message.case_id == matched.case_id,
            Message.gmail_id == message.gmail_id,
            Message.direction == MessageDirection.inbound,
        )
    )
    if existing is not None:
        return IngestResult(
            gmail_id=message.gmail_id,
            case_id=existing.case_id,
            account_id=matched.account_id,
            recipient_check=matched.recipient_check.value,
            method=matched.method,
            unsorted=matched.unsorted,
            message_id=existing.id,
            extraction="skipped",
        )
    row = Message(
        case_id=matched.case_id,
        direction=MessageDirection.inbound,
        gmail_id=message.gmail_id,
        thread_id=message.thread_id or None,
        rfc_message_id=message.rfc_message_id or None,
        from_addr=message.from_addr,
        reply_to=message.reply_to,
        to_addrs=list(message.to_addrs),
        subject=message.subject,
        latest_text=extracted.latest_text,
        full_text_sha256=extracted.full_sha256,
        received_at=message.received_at,
        recipient_check=matched.recipient_check,
    )
    session.add(row)
    session.flush()
    extraction = _check_outcome(
        session, matched.case_id, matched.account_id, matched.recipient_check
    )
    if bus is not None:
        bus.publish(
            session,
            matched.case_id,
            "mail_ingested",
            {
                "gmail_id": message.gmail_id,
                "recipient_check": matched.recipient_check.value,
                "match": matched.method,
                "unsorted": matched.unsorted,
            },
            actor="Afterward",
        )
    if matched.unsorted and tray is not None:
        tray.add(message, "no_account")
    return IngestResult(
        gmail_id=message.gmail_id,
        case_id=matched.case_id,
        account_id=matched.account_id,
        recipient_check=matched.recipient_check.value,
        method=matched.method,
        unsorted=matched.unsorted,
        message_id=row.id,
        extraction=extraction,
        new=True,
    )


def unsorted_for(session: Session, case_id: UUID) -> list[Message]:
    """Persisted inbound mail on this case with no single account match."""
    return list_unsorted(session, case_id)


def _check_outcome(
    session: Session, case_id: UUID, account_id: UUID | None, check: RecipientCheck
) -> ExtractionState:
    """Deterministic check of the approved plan against stored commitments. No model call."""
    if account_id is None or check is not RecipientCheck.approved:
        return "skipped"
    plan = session.scalar(
        select(Plan)
        .where(Plan.account_id == account_id, Plan.status == PlanStatus.approved)
        .order_by(Plan.version.desc())
    )
    account = session.get(Account, account_id)
    if plan is None or account is None:
        return "skipped"
    profile = session.get(ProviderProfile, account.provider_id) if account.provider_id else None
    rows = list(session.scalars(select(Commitment).where(Commitment.account_id == account_id)))
    views = [
        CommitmentView(
            action=row.action.value,
            status=row.status.value,
            interpretation=row.interpretation.value,
            facts=tuple(
                FactView(
                    key=str(f.get("key") or ""),
                    value=str(f.get("value") or ""),
                    evidence_quote=str(f.get("evidence_quote") or ""),
                )
                for f in (row.facts or [])
                if isinstance(f, dict)
            ),
            negated=bool(row.negated),
            at=row.created_at or datetime.now(UTC),
            evidence_quote=row.evidence_quote or "",
        )
        for row in rows
    ]
    verdict = outcome_check(
        PlanView(
            action=plan.action.value,
            conditions=conditions_from(list(plan.conditions or [])),
            completion_evidence=tuple(
                str(e) for e in (profile.completion_evidence if profile else [])
            ),
        ),
        views,
    )
    session.add(
        OutcomeCheck(
            case_id=case_id,
            account_id=account_id,
            plan_version=plan.version,
            results={**verdict.results, "unauthorised": list(verdict.extras)},
            verdict=verdict.verdict,
        )
    )
    session.flush()
    return "called"


async def process_inbound(
    session: Session,
    messages: list[MailMessage],
    *,
    ai: object | None,
    bus: EventBus | None = None,
    bound_case_id: UUID | None = None,
    tray: UnsortedTray | None = None,
) -> list[IngestResult]:
    """Store every message; run approved, matched replies through the engine pipeline.

    Raises MailError before storing a message that needs reading when `ai` is None,
    so the poll job fails visibly and the message is fetched again next time.
    """
    holding = tray if tray is not None else UnsortedTray()
    results: list[IngestResult] = []
    for message in messages:
        matched = match_message(session, message, bound_case_id=bound_case_id)
        reads = (
            matched.case_id is not None
            and matched.account_id is not None
            and matched.recipient_check is RecipientCheck.approved
            and not _already_stored(session, matched.case_id, message.gmail_id)
        )
        if not reads:
            results.append(
                ingest_message(session, message, bus=bus, bound_case_id=bound_case_id, tray=holding)
            )
            continue
        if ai is None:
            raise MailError("An approved reply needs reading but no AI client is configured")
        assert matched.case_id is not None and matched.account_id is not None
        results.append(
            await _read_approved(
                session, message, matched.case_id, matched.account_id, matched.method, ai, bus
            )
        )
    return results


def _already_stored(session: Session, case_id: UUID, gmail_id: str) -> bool:
    return (
        session.scalar(
            select(Message.id).where(
                Message.case_id == case_id,
                Message.gmail_id == gmail_id,
                Message.direction == MessageDirection.inbound,
            )
        )
        is not None
    )


async def _read_approved(
    session: Session,
    message: MailMessage,
    case_id: UUID,
    account_id: UUID,
    method: str,
    ai: object,
    bus: EventBus | None,
) -> IngestResult:
    case = session.get(Case, case_id)
    account = session.get(Account, account_id)
    if case is None or account is None:
        raise MailError("Matched case or account is missing")
    profile = session.get(ProviderProfile, account.provider_id) if account.provider_id else None
    plan = session.scalar(
        select(Plan)
        .where(Plan.account_id == account.id, Plan.status == PlanStatus.approved)
        .order_by(Plan.version.desc())
    )
    before = set(
        session.scalars(
            select(Message.id).where(
                Message.case_id == case_id, Message.direction == MessageDirection.inbound
            )
        )
    )
    raw = message.full_text or message.latest_text
    outcome = await process_reply(
        session,
        case=case,
        account=account,
        plan=plan,
        raw_text=raw,
        from_addr=message.from_addr,
        reply_to=message.reply_to,
        ai=ai,
        account_refs=[account.account_ref],
        approved_recipients=[str(a) for a in (profile.approved_recipients if profile else [])],
        completion_evidence=tuple(str(e) for e in (profile.completion_evidence if profile else [])),
        received_at=message.received_at,
        subject=message.subject,
        to_addrs=list(message.to_addrs),
    )
    stored = session.scalar(
        select(Message).where(
            Message.case_id == case_id,
            Message.direction == MessageDirection.inbound,
            Message.id.not_in(before) if before else Message.id.is_not(None),
        )
    )
    if stored is not None:
        stored.gmail_id = message.gmail_id
        stored.thread_id = message.thread_id or None
        stored.rfc_message_id = message.rfc_message_id or None
    session.flush()
    if bus is not None:
        bus.publish(
            session,
            case_id,
            "mail_ingested",
            {
                "gmail_id": message.gmail_id,
                "recipient_check": outcome.recipient_check.value,
                "match": method,
                "unsorted": False,
            },
            actor="Afterward",
        )
    return IngestResult(
        gmail_id=message.gmail_id,
        case_id=case_id,
        account_id=account_id,
        recipient_check=outcome.recipient_check.value,
        method=method,
        unsorted=False,
        message_id=stored.id if stored else None,
        extraction="called",
        new=True,
    )
