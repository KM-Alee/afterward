"""Engine-side job executors: followup, final_bill_check, refund_evidence_check, digest.

Each runs only after the runner's preflight passed. None sends to a provider itself:
a follow-up queues a `send_request` job that carries the same approved plan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.jobs import case_now, enqueue
from app.engine.runner import RunContext, register_executor
from app.engine.status import finish_summary
from app.models import (
    Account,
    Case,
    Event,
    Job,
    MoneyItem,
    MoneyItemStatus,
    MoneyKind,
)

MAX_REFUND_CHECKS = 3
REFUND_RECHECK_DAYS = 7
DIGEST_DAYS = 7
_OPEN_BILL = {
    MoneyItemStatus.needs_review,
    MoneyItemStatus.likely_error,
    MoneyItemStatus.balance_owed,
}
_OPEN_REFUND = {MoneyItemStatus.refund_promised, MoneyItemStatus.issued_awaiting_receipt}


def _case(session: Session, job: Job) -> Case:
    case = session.get(Case, job.case_id)
    if case is None:
        raise LookupError("case_missing")
    return case


def _audit(session: Session, job: Job, kind: str, **payload: object) -> None:
    session.add(Event(case_id=job.case_id, kind=kind, actor="engine", payload=payload))


async def _tell(ctx: RunContext, text: str) -> bool:
    return bool(ctx.notify is not None and await ctx.notify(text))


async def run_followup(session: Session, job: Job, ctx: RunContext) -> None:
    """Queue the follow-up send under the same plan and approval. Never sends directly."""
    del ctx
    case = _case(session, job)
    payload = dict(job.payload or {})
    reason = dict(payload.get("reason") or {})
    enqueue(
        session,
        case_id=job.case_id,
        kind="send_request",
        run_at_case_time=case_now(case, datetime.now(UTC)),
        idem_key=f"send:{job.idem_key}",
        payload={
            "plan_id": payload.get("plan_id"),
            "plan_version": payload.get("plan_version"),
            "plan_hash": payload.get("plan_hash"),
            "approval_id": payload.get("approval_id"),
            "outbound": True,
            "followup": True,
            "followup_job_id": str(job.id),
            "account_id": reason.get("account_id"),
            "reason": reason,
        },
    )
    _audit(session, job, "followup.queued", job_id=str(job.id))


async def run_final_bill_check(session: Session, job: Job, ctx: RunContext) -> None:
    """Tell the family about charges or balances that still need a person's eyes."""
    account_id = UUID(str((job.payload or {}).get("account_id")))
    account = session.get(Account, account_id)
    if account is None or account.case_id != job.case_id:
        raise LookupError("account_missing")
    items = session.scalars(
        select(MoneyItem).where(
            MoneyItem.account_id == account.id,
            MoneyItem.kind.in_([MoneyKind.charge, MoneyKind.balance]),
            MoneyItem.status.in_(_OPEN_BILL),
        )
    ).all()
    _audit(session, job, "final_bill.checked", account_id=str(account.id), open_items=len(items))
    if items:
        await _tell(
            ctx,
            f"{account.service_label}: {len(items)} charge(s) still need a look before "
            "this account counts as settled. Nothing has been paid or disputed.",
        )


async def run_refund_evidence_check(session: Session, job: Job, ctx: RunContext) -> None:
    """A promised refund is not received until a statement shows it. Ask again, a few times."""
    payload = job.payload or {}
    item = session.get(MoneyItem, UUID(str(payload["money_item_id"])))
    if item is None or item.case_id != job.case_id:
        raise LookupError("money_item_missing")
    count = int(payload.get("check_n", 1))
    _audit(session, job, "refund.checked", money_item_id=str(item.id), n=count)
    if item.status not in _OPEN_REFUND:
        return
    await _tell(
        ctx,
        "A refund was promised but I have no statement showing it arrived. "
        "A line from your bank statement would let me mark it received.",
    )
    if count >= MAX_REFUND_CHECKS:
        return
    case = _case(session, job)
    enqueue(
        session,
        case_id=job.case_id,
        kind="refund_evidence_check",
        run_at_case_time=case_now(case, datetime.now(UTC)) + timedelta(days=REFUND_RECHECK_DAYS),
        idem_key=f"refund_evidence:{item.id}:n{count + 1}",
        payload={**payload, "check_n": count + 1},
    )


async def run_digest(session: Session, job: Job, ctx: RunContext) -> None:
    """Weekly summary from stored dimensions; counts come from code, not a model."""
    case = _case(session, job)
    accounts = session.scalars(select(Account).where(Account.case_id == case.id)).all()
    summary = finish_summary([(account, True) for account in accounts])
    sent = await _tell(ctx, f"Weekly summary for {case.deceased_name}'s accounts. {summary.text}")
    _audit(session, job, "digest.sent" if sent else "digest.skipped", accounts=len(accounts))
    n = int((job.payload or {}).get("digest_n", 1))
    enqueue(
        session,
        case_id=job.case_id,
        kind="digest",
        run_at_case_time=case_now(case, datetime.now(UTC)) + timedelta(days=DIGEST_DAYS),
        idem_key=f"digest:{case.id}:n{n + 1}",
        payload={"digest_n": n + 1, "touches_family": True},
    )


def register_engine_executors() -> None:
    """Idempotent: install the engine's executors on the runner."""
    register_executor("followup", run_followup)
    register_executor("final_bill_check", run_final_bill_check)
    register_executor("refund_evidence_check", run_refund_evidence_check)
    register_executor("digest", run_digest)


register_engine_executors()
