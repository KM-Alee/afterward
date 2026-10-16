"""The live reply path: recipient check, latest text, extraction, verification, outcome."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.ai.prompts import REPLY_READER_INSTRUCTIONS
from app.ai.schemas import CommitmentOut, ReplyOut
from app.ai.verify import (
    match_account_hint,
    quote_in_text,
    strip_quoted_history,
    verify_reply,
)
from app.contracts import ChatMessage
from app.engine.outcome import (
    CommitmentView,
    FactView,
    MoneyAssessment,
    PlanView,
    Verdict,
    assess_money,
    conditions_from,
    outcome_check,
)
from app.models import (
    Account,
    Case,
    Commitment,
    CommitmentScope,
    CommitmentStatus,
    DocsStatus,
    Interpretation,
    Message,
    MessageDirection,
    MoneyItem,
    MoneyKind,
    OutcomeCheck,
    Plan,
    PlanAction,
    RecipientCheck,
    ServiceStatus,
)


@dataclass
class PipelineResult:
    """What the reply changed. Recipients are never taken from the message."""

    recipient_check: RecipientCheck
    held: bool
    latest_text: str
    verdict: Verdict | None = None
    money: MoneyAssessment | None = None
    documents: DocsStatus | None = None
    next_step: dict[str, object] | None = None
    disclosed: bool = False
    matched_ref: str | None = None
    reply: ReplyOut | None = None


@dataclass
class HeldDocument:
    """A vault form the requirement check can see. The blob stays out of this record."""

    doc_type: str
    form: str


def _as_reply(raw: object) -> ReplyOut:
    if isinstance(raw, ReplyOut):
        return raw
    payload = raw if isinstance(raw, dict) else raw.model_dump()  # type: ignore[union-attr]
    return ReplyOut.model_validate(payload)


def _needs_quote_retry(before: ReplyOut, after: ReplyOut) -> bool:
    """True when a quote was dropped or a clear reading became ambiguous."""
    for left, right in zip(before.commitments, after.commitments, strict=False):
        if left.evidence_quote.strip() and not right.evidence_quote.strip():
            return True
        if left.interpretation == "clear" and right.interpretation == "ambiguous":
            return True
    return False


_NAMES_A_NUMBER = re.compile(r"\d{3,}")


def bind_thread_account(
    reply: ReplyOut, account_refs: Sequence[str], thread_ref: str | None
) -> ReplyOut:
    """A reply on a thread code already routed to one account names that account.

    Only a hint that names no account number is bound. A hint naming another number, or
    several, is left alone and stays ambiguous after verification.
    """
    if not thread_ref or thread_ref not in account_refs:
        return reply
    bound = []
    for commitment in reply.commitments:
        hint = commitment.account_hint
        if match_account_hint(hint, list(account_refs)) is None and not _NAMES_A_NUMBER.search(
            hint
        ):
            commitment = commitment.model_copy(update={"account_hint": thread_ref})
        bound.append(commitment)
    return reply.model_copy(update={"commitments": bound})


async def extract_verified_reply(
    ai: Any,
    latest: str,
    account_refs: Sequence[str],
    *,
    thread_ref: str | None = None,
) -> ReplyOut:
    """Read a reply, then retry once if the quotes are not in the text."""
    messages = extraction_messages(latest)
    proposal = _as_reply(await ai.structured("reply_reader", ReplyOut, messages))
    proposal = bind_thread_account(proposal, account_refs, thread_ref)
    verified = verify_reply(proposal, latest, list(account_refs))
    if not _needs_quote_retry(proposal, verified):
        return verified
    retry = [
        *messages,
        ChatMessage(
            role="user",
            content=(
                "The evidence_quote values were not exact copies of the provider text. "
                "Copy each evidence_quote as a contiguous substring of the text below. "
                "will is not completed. A voicemail that will be reset "
                "is voicemail_preserved=false. "
                "A new contract length is contract_months.\n" + latest
            ),
        ),
    ]
    try:
        second = _as_reply(await ai.structured("reply_reader", ReplyOut, retry))
    except Exception:
        return verified
    second = bind_thread_account(second, account_refs, thread_ref)
    return verify_reply(second, latest, list(account_refs))


def extraction_messages(latest_text: str) -> list[ChatMessage]:
    """The messages live mail and the proof runner both send to the reply reader."""
    return [
        ChatMessage(role="system", content=REPLY_READER_INSTRUCTIONS),
        ChatMessage(role="user", content=latest_text),
    ]


def check_recipient(
    from_addr: str,
    reply_to: str | None,
    approved_recipients: Sequence[str],
) -> RecipientCheck:
    """Exact address match. A different Reply-To, even on a familiar domain, does not pass."""
    approved = {item.casefold() for item in approved_recipients}
    if from_addr.casefold() not in approved:
        return RecipientCheck.unapproved
    if reply_to and reply_to.casefold() not in approved:
        return RecipientCheck.reply_to_mismatch
    return RecipientCheck.approved


def match_document_requirement(
    required_form: str,
    held_form: str | None,
) -> tuple[DocsStatus, dict[str, object]]:
    """A photo never satisfies a certified copy. The next step is prepared instead of sending."""
    if held_form is None:
        return DocsStatus.requested, {
            "owner": "family",
            "action": "Provide the document",
            "due_date": None,
        }
    if required_form in {"certified_copy", "original"} and held_form in {"photo", "scan"}:
        return DocsStatus.requirement_unmet, {
            "owner": "family",
            "action": "Post a certified copy. A photo is not a certified copy.",
            "due_date": None,
        }
    if required_form == held_form or (
        required_form == "certified_copy" and held_form == "certified_copy_held"
    ):
        return DocsStatus.accepted, {
            "owner": "provider",
            "action": "Requirement met",
            "due_date": None,
        }
    return DocsStatus.requirement_unmet, {
        "owner": "family",
        "action": "The held form does not meet the requirement",
        "due_date": None,
    }


def _views(commitments: Sequence[CommitmentOut], at: datetime) -> list[CommitmentView]:
    return [
        CommitmentView(
            action=item.action,
            status=item.status,
            interpretation=item.interpretation,
            facts=tuple(
                FactView(key=fact.key, value=fact.value, evidence_quote=fact.evidence_quote)
                for fact in item.facts
            ),
            negated=item.negated,
            at=at,
            evidence_quote=item.evidence_quote,
            scope=item.scope,
        )
        for item in commitments
    ]


def _apply_service(account: Account, action: str, verdict: Verdict) -> None:
    if verdict.verdict == "needs_decision":
        account.next_step = {"owner": "family", "action": "Fresh decision needed", "due_date": None}
        return
    if verdict.verdict == "resolved":
        resolved = {
            "close": ServiceStatus.closed,
            "transfer": ServiceStatus.transferred,
            "freeze": ServiceStatus.frozen,
        }
        if action in resolved:
            account.status_service = resolved[action]
        account.next_step = {"owner": "afterward", "action": "None", "due_date": None}
        return
    if verdict.results.get("action") == "acknowledged":
        account.status_service = ServiceStatus.acknowledged
    elif verdict.results.get("action") == "blocked":
        account.status_service = ServiceStatus.blocked
        account.next_step = {
            "owner": "provider",
            "action": "Blocked on a requirement",
            "due_date": None,
        }


def _decimal(value: str) -> Decimal:
    cleaned = "".join(character for character in value if character.isdigit() or character == ".")
    return Decimal(cleaned or "0")


def _money_for(
    commitment: CommitmentOut,
    *,
    closure_effective_date: date | None,
) -> MoneyAssessment | None:
    if commitment.interpretation != "clear":
        return None
    refund = next((fact for fact in commitment.facts if fact.key == "refund_amount"), None)
    if refund is not None or commitment.action == "refund":
        issued = "issued" in commitment.evidence_quote.casefold()
        return assess_money(
            kind="refund",
            promised=True,
            issued=issued,
            statement_evidence=False,
        )
    period = next((fact for fact in commitment.facts if fact.key == "service_period_start"), None)
    if period is None:
        return None
    try:
        start = date.fromisoformat(period.value)
    except ValueError:
        return None
    return assess_money(
        kind="charge",
        service_period_start=start,
        closure_effective_date=closure_effective_date,
    )


def can_merge(left: Account, right: Account) -> bool:
    """Two accounts merge only when the case and the reference are the same."""
    same_case = left.case_id == right.case_id
    same_ref = left.account_ref.casefold() == right.account_ref.casefold()
    return same_case and same_ref


@dataclass
class _Persist:
    session: Session
    case: Case
    account: Account
    raw_text: str
    latest_text: str
    from_addr: str
    reply_to: str | None
    to_addrs: list[str]
    subject: str
    received_at: datetime
    recipient_check: RecipientCheck
    message: Message | None = field(default=None)


def _store_message(bundle: _Persist) -> Message:
    message = Message(
        case_id=bundle.case.id,
        direction=MessageDirection.inbound,
        from_addr=bundle.from_addr,
        reply_to=bundle.reply_to,
        to_addrs=bundle.to_addrs,
        subject=bundle.subject,
        latest_text=bundle.latest_text,
        full_text_sha256=hashlib.sha256(bundle.raw_text.encode()).hexdigest(),
        received_at=bundle.received_at,
        recipient_check=bundle.recipient_check,
    )
    bundle.session.add(message)
    bundle.session.flush()
    return message


async def process_reply(
    session: Session,
    *,
    case: Case,
    account: Account,
    plan: Plan | None,
    raw_text: str,
    from_addr: str,
    reply_to: str | None,
    ai: Any,
    account_refs: Sequence[str],
    approved_recipients: Sequence[str],
    held_documents: Sequence[HeldDocument] = (),
    completion_evidence: Sequence[str] = (),
    closure_effective_date: date | None = None,
    received_at: datetime | None = None,
    subject: str = "",
    to_addrs: Sequence[str] = (),
) -> PipelineResult:
    """Run one provider reply through the same steps live mail will use."""
    if received_at is None:
        received_at = datetime.now(UTC)
    check = check_recipient(from_addr, reply_to, approved_recipients)
    latest = strip_quoted_history(raw_text)
    held = check is not RecipientCheck.approved
    result = PipelineResult(recipient_check=check, held=held, latest_text=latest)
    if result.held:
        _store_message(
            _Persist(
                session=session,
                case=case,
                account=account,
                raw_text=raw_text,
                latest_text=latest,
                from_addr=from_addr,
                reply_to=reply_to,
                to_addrs=list(to_addrs),
                subject=subject,
                received_at=received_at,
                recipient_check=check,
            )
        )
        account.next_step = {
            "owner": "family",
            "action": "Hold and warn. Do not disclose documents.",
            "due_date": None,
        }
        result.next_step = dict(account.next_step)
        return result
    verified = await extract_verified_reply(ai, latest, account_refs)
    result.reply = verified
    message = _store_message(
        _Persist(
            session=session,
            case=case,
            account=account,
            raw_text=raw_text,
            latest_text=latest,
            from_addr=from_addr,
            reply_to=reply_to,
            to_addrs=list(to_addrs),
            subject=subject,
            received_at=received_at,
            recipient_check=check,
        )
    )
    matched: list[CommitmentOut] = []
    for commitment in verified.commitments:
        ref = match_account_hint(commitment.account_hint, list(account_refs))
        attached = ref == account.account_ref
        if attached:
            result.matched_ref = ref
            matched.append(commitment)
        session.add(
            Commitment(
                case_id=case.id,
                message_id=message.id,
                account_id=account.id if attached else None,
                action=PlanAction(commitment.action),
                status=CommitmentStatus(commitment.status),
                conditions=list(commitment.conditions_or_requirements),
                facts=[fact.model_dump() for fact in commitment.facts],
                negated=commitment.negated,
                scope=CommitmentScope(commitment.scope),
                effective_date=commitment.effective_date,
                evidence_quote=commitment.evidence_quote,
                quote_verified=bool(commitment.evidence_quote)
                and quote_in_text(commitment.evidence_quote, latest),
                interpretation=Interpretation(commitment.interpretation),
            )
        )
    session.flush()
    if plan is not None and matched:
        verdict = outcome_check(
            PlanView(
                action=plan.action.value,
                conditions=conditions_from(plan.conditions or []),
                completion_evidence=tuple(completion_evidence),
            ),
            _views(matched, received_at),
        )
        result.verdict = verdict
        session.add(
            OutcomeCheck(
                case_id=case.id,
                account_id=account.id,
                plan_version=plan.version,
                results={**verdict.results, "unauthorised": list(verdict.extras)},
                verdict=verdict.verdict,
            )
        )
        _apply_service(account, plan.action.value, verdict)
        for commitment in matched:
            assessment = _money_for(commitment, closure_effective_date=closure_effective_date)
            if assessment is None:
                continue
            result.money = assessment
            amount = "0"
            period_start = None
            for fact in commitment.facts:
                if fact.key == "refund_amount":
                    amount = fact.value
                if fact.key == "service_period_start":
                    try:
                        period_start = date.fromisoformat(fact.value)
                    except ValueError:
                        period_start = None
            charge = assessment.reason in {"needs_review", "service_after_closure"}
            session.add(
                MoneyItem(
                    case_id=case.id,
                    account_id=account.id,
                    kind=MoneyKind.charge if charge else MoneyKind.refund,
                    amount=_decimal(amount),
                    service_period_start=period_start,
                    status=assessment.status,
                    evidence=commitment.evidence_quote,
                )
            )
            account.status_money = assessment.status
            if not assessment.dispute_proposed:
                account.status_money = assessment.status
    if verified.asks_for_documents:
        request = verified.asks_for_documents[0]
        held = next(
            (item.form for item in held_documents if item.doc_type == request.document_type),
            None,
        )
        status, step = match_document_requirement(request.required_form, held)
        account.status_docs = status
        if status is DocsStatus.requirement_unmet:
            account.next_step = step
        result.documents = status
        result.next_step = step
        result.disclosed = False
        if request.recipient_mentioned:
            result.disclosed = False
    session.flush()
    return result
