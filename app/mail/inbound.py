"""Store a new message and call Agent A's extraction when it is importable.

The adapter does nothing harmful when those functions are still stubs. Model
output is never copied into approved recipients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import ReplyOut
from app.contracts import EventBus, MailMessage
from app.mail.match import MatchResult, list_unsorted, match_message
from app.mail.parse import extract_text
from app.models import (
    Commitment,
    CommitmentScope,
    CommitmentStatus,
    Interpretation,
    Message,
    MessageDirection,
    OutcomeCheck,
    Plan,
    PlanAction,
    PlanStatus,
)

ExtractionState = Literal["called", "unavailable", "skipped"]


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


def ingest_messages(
    session: Session,
    messages: list[MailMessage],
    *,
    bus: EventBus | None = None,
    bound_case_id: UUID | None = None,
    tray: UnsortedTray | None = None,
) -> list[IngestResult]:
    """Match, store and, when approved, call extraction. Recipients stay put."""
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
    extraction = _maybe_extract(session, row, matched, extracted.latest_text)
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
    )


def unsorted_for(session: Session, case_id: UUID) -> list[Message]:
    """Persisted inbound mail on this case with no single account match."""
    return list_unsorted(session, case_id)


def _maybe_extract(
    session: Session,
    row: Message,
    matched: MatchResult,
    latest_text: str,
) -> ExtractionState:
    if matched.recipient_check.value != "approved" or matched.account_id is None:
        return "skipped"
    outcome_check, verify = extraction_hooks()
    if outcome_check is None and verify is None:
        return "unavailable"
    proposal = _call_verify(verify, latest_text)
    if isinstance(proposal, ReplyOut):
        _store_commitments(session, row, matched, proposal)
    plan = _approved_plan(session, matched.account_id)
    if plan is None:
        return "skipped"
    commitments = list(
        session.scalars(select(Commitment).where(Commitment.account_id == matched.account_id))
    )
    verdict = _call_outcome(outcome_check, plan, commitments)
    if verdict is not None and plan is not None:
        verdict_name, results = verdict
        session.add(
            OutcomeCheck(
                case_id=matched.case_id,
                account_id=matched.account_id,
                plan_version=plan.version,
                results=results,
                verdict=verdict_name,
            )
        )
        session.flush()
    return "called"


def extraction_hooks() -> tuple[object | None, object | None]:
    """Return Agent A's callables when they exist. Missing stubs stay None."""
    outcome_check = _callable("app.engine.outcome", "outcome_check")
    verify = None
    for name in ("verify_reply", "verify_quotes", "verify"):
        verify = _callable("app.ai.verify", name)
        if verify is not None:
            break
    return outcome_check, verify


def _callable(module_name: str, attr: str) -> object | None:
    try:
        module = __import__(module_name, fromlist=[attr])
    except ImportError:
        return None
    candidate = getattr(module, attr, None)
    if callable(candidate):
        return candidate
    return None


def _call_verify(verify: object | None, latest_text: str) -> object | None:
    if verify is None:
        return None
    try:
        return verify(latest_text)  # type: ignore[operator]
    except TypeError:
        return None


def _commitment_views(rows: list[Commitment]) -> list[object]:
    from app.engine.outcome import CommitmentView, FactView

    views: list[object] = []
    for row in rows:
        facts = []
        for fact in row.facts or []:
            if isinstance(fact, dict):
                facts.append(
                    FactView(
                        key=str(fact.get("key") or ""),
                        value=str(fact.get("value") or ""),
                        evidence_quote=str(fact.get("evidence_quote") or ""),
                    )
                )
        action = row.action.value if hasattr(row.action, "value") else str(row.action)
        status = row.status.value if hasattr(row.status, "value") else str(row.status)
        interpretation = (
            row.interpretation.value
            if hasattr(row.interpretation, "value")
            else str(row.interpretation)
        )
        views.append(
            CommitmentView(
                action=action,
                status=status,
                interpretation=interpretation,
                facts=tuple(facts),
                negated=bool(row.negated),
                at=row.created_at or datetime.now(UTC),
                evidence_quote=row.evidence_quote or "",
            )
        )
    return views


def _plan_view(plan: Plan) -> object:
    from app.engine.outcome import PlanView, conditions_from

    action = plan.action.value if hasattr(plan.action, "value") else str(plan.action)
    return PlanView(
        action=action,
        conditions=conditions_from(list(plan.conditions or [])),
        completion_evidence=(),
    )


def _call_outcome(
    outcome_check: object | None,
    plan: Plan | None,
    commitments: list[Commitment],
) -> tuple[str, dict[str, object]] | None:
    if outcome_check is None or plan is None:
        return None
    try:
        result = outcome_check(plan, commitments)  # type: ignore[operator]
    except (TypeError, AttributeError):
        result = outcome_check(_plan_view(plan), _commitment_views(commitments))  # type: ignore[operator]
    return _verdict(result)


def _verdict(result: object) -> tuple[str, dict[str, object]] | None:
    if isinstance(result, str) and result:
        return result, {}
    if isinstance(result, dict):
        name = result.get("verdict")
        raw = result.get("results")
        if not isinstance(name, str) or not name:
            return None
        results = raw if isinstance(raw, dict) else {}
        return name, _json_object(results)
    name = getattr(result, "verdict", None)
    raw = getattr(result, "results", {})
    if isinstance(name, str) and name:
        results = raw if isinstance(raw, dict) else {}
        return name, _json_object(results)
    return None


def _json_object(value: dict[object, object]) -> dict[str, object]:
    return {str(key): _jsonish(item) for key, item in value.items()}


def _jsonish(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonish(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonish(item) for item in value]
    return str(value)


def _approved_plan(session: Session, account_id: UUID) -> Plan | None:
    return session.scalar(
        select(Plan)
        .where(Plan.account_id == account_id, Plan.status == PlanStatus.approved)
        .order_by(Plan.version.desc())
    )


def _store_commitments(
    session: Session,
    row: Message,
    matched: MatchResult,
    proposal: ReplyOut,
) -> None:
    """Store proposed commitments. Document asks do not change recipients."""
    if matched.case_id is None or matched.account_id is None:
        return
    for item in proposal.commitments:
        session.add(
            Commitment(
                case_id=matched.case_id,
                message_id=row.id,
                account_id=matched.account_id,
                action=PlanAction(item.action),
                status=CommitmentStatus(item.status),
                conditions=list(item.conditions_or_requirements),
                facts=[fact.model_dump() for fact in item.facts],
                negated=item.negated,
                scope=CommitmentScope(item.scope),
                effective_date=item.effective_date,
                evidence_quote=item.evidence_quote,
                quote_verified=False,
                interpretation=Interpretation(item.interpretation),
            )
        )
        session.flush()
