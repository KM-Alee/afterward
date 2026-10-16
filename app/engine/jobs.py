"""Durable jobs. Leases use wall-clock time. Due time and business days use the case clock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.contracts import JOB_KINDS, CaseClock, ContractError
from app.engine.plans import latest_plan
from app.engine.policy import decide
from app.models import (
    Approval,
    ApprovalStatus,
    Case,
    Commitment,
    Decision,
    DecisionStatus,
    Job,
    JobStatus,
    Member,
    MemberRole,
    MoneyItem,
    MoneyItemStatus,
    Monitoring,
    Plan,
    PlanStatus,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
LEASE_SECONDS = 60
_OUTBOUND_KINDS = {"send_request", "followup"}
_FAMILY_KINDS = {"digest"}
_MAILBOX_KINDS = {
    "inbox_poll",
    "send_request",
    "followup",
    "reconcile_action",
    "final_bill_check",
    "refund_evidence_check",
}
_NEEDS_APPROVAL = {"send_request", "followup"}

_LEASE_SQL = """
SELECT j.id FROM jobs j
JOIN cases c ON c.id = j.case_id
WHERE (
    j.status = 'pending'
    AND j.run_at_case_time <= now() + make_interval(secs => c.clock_offset_s)
) OR (
    j.status = 'running'
    AND j.lease_until IS NOT NULL
    AND j.lease_until < now()
)
ORDER BY j.run_at_case_time
FOR UPDATE OF j SKIP LOCKED
LIMIT :limit
"""


@dataclass(frozen=True)
class PreflightResult:
    """`ok` is false when the job was cancelled. `reason` is a short rule code."""

    ok: bool
    reason: str = ""


def case_now(case: CaseClock, wall: datetime) -> datetime:
    """Timezone-aware case time. The offset is demo-only and lives on the case."""
    if wall.tzinfo is None:
        raise ValueError("case clock requires a timezone-aware wall time")
    return wall + timedelta(seconds=int(case.clock_offset_s))


def add_business_days(start: datetime, days: int) -> datetime:
    """Move forward by business days. Saturday and Sunday do not count."""
    if days < 0:
        raise ValueError("business days must be zero or more")
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def is_due(job: Job, case: CaseClock, wall: datetime) -> bool:
    """A pending job is due in case time. A running job is due again when its lease expired."""
    if job.status is JobStatus.running and job.lease_until is not None and job.lease_until < wall:
        return True
    if job.status is not JobStatus.pending:
        return False
    return job.run_at_case_time <= wall + timedelta(seconds=int(case.clock_offset_s))


def enqueue(
    session: Session,
    *,
    case_id: UUID,
    kind: str,
    run_at_case_time: datetime,
    idem_key: str,
    payload: dict[str, Any] | None = None,
) -> Job:
    """Insert a job, or return the existing row when the idempotency key is already used."""
    if kind not in JOB_KINDS:
        raise ContractError("Unknown job kind")
    if not idem_key:
        raise ContractError("Job idempotency key is required")
    existing = session.scalar(select(Job).where(Job.idem_key == idem_key))
    if existing is not None:
        return existing
    session.execute(
        pg_insert(Job)
        .values(
            id=uuid4(),
            case_id=case_id,
            kind=kind,
            run_at_case_time=run_at_case_time,
            payload=dict(payload or {}),
            status=JobStatus.pending,
            idem_key=idem_key,
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_jobs_idem_key")
    )
    session.flush()
    winner = session.scalar(select(Job).where(Job.idem_key == idem_key))
    if winner is None:
        raise ContractError("Job was not stored")
    return winner


def lease_due(
    session: Session,
    *,
    wall: datetime | None = None,
    limit: int = 10,
    lease_seconds: int = LEASE_SECONDS,
) -> list[Job]:
    """Lock due jobs with FOR UPDATE SKIP LOCKED and hold each lease on the wall clock."""
    del wall  # The picker uses PostgreSQL now(), which is the wall clock, not case time.
    rows = session.execute(text(_LEASE_SQL), {"limit": limit}).scalars().all()
    jobs: list[Job] = []
    until = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    for job_id in rows:
        job = session.get(Job, job_id)
        if job is None:
            continue
        job.status = JobStatus.running
        job.lease_until = until
        job.attempts += 1
        jobs.append(job)
    session.flush()
    return jobs


def complete_job(job: Job) -> None:
    """The work finished. The lease is released."""
    job.status = JobStatus.succeeded
    job.lease_until = None
    job.last_error = None


def fail_job(session: Session, job: Job, reason: str, *, wall: datetime) -> None:
    """Retry with backoff until MAX_ATTEMPTS, then mark the job failed."""
    if job.status is not JobStatus.running:
        job.attempts += 1
    job.lease_until = None
    job.last_error = reason[:200]
    if job.attempts >= MAX_ATTEMPTS:
        job.status = JobStatus.failed
        return
    case = session.get(Case, job.case_id)
    if case is None:
        job.status = JobStatus.failed
        return
    job.status = JobStatus.pending
    job.run_at_case_time = case_now(case, wall) + timedelta(seconds=2**job.attempts)


def cancel_job(job: Job, reason: str) -> None:
    """Stop the job and keep the rule code on the row."""
    job.status = JobStatus.cancelled
    job.lease_until = None
    job.last_error = reason[:200]
    logger.info(
        "job cancelled",
        extra={"kind": "job.cancelled", "job_id": str(job.id), "reason": reason[:80]},
    )


def schedule_followup(
    session: Session,
    *,
    case: Case,
    account_id: UUID,
    plan: Plan,
    approval_id: UUID,
    sent_at: datetime,
    window_bd: int,
    n: int = 1,
) -> Job:
    """Schedule follow-up n after the provider's response window, in case business days."""
    return enqueue(
        session,
        case_id=case.id,
        kind="followup",
        run_at_case_time=add_business_days(sent_at, window_bd),
        idem_key=f"followup:{account_id}:planv{plan.version}:n{n}",
        payload={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "plan_hash": plan.hash,
            "approval_id": str(approval_id),
            "outbound": True,
            "reason": {
                "type": "awaiting_reply",
                "account_id": str(account_id),
                "since": sent_at.isoformat(),
            },
        },
    )


def _ask_for_followup(session: Session, case: Case, job: Job) -> None:
    """Gentle follow-ups ask the family. The job stays pending instead of vanishing."""
    existing = session.scalar(
        select(Decision.id).where(Decision.case_id == case.id, Decision.kind == "followup")
    )
    if existing is not None:
        return
    session.add(
        Decision(
            case_id=case.id,
            kind="followup",
            payload={"job_id": str(job.id)},
            options=[
                {"id": "send", "label": "Send follow-up"},
                {"id": "not_now", "label": "Not now"},
            ],
            plan_hash=(job.payload or {}).get("plan_hash"),
            status=DecisionStatus.open,
        )
    )


def _flag(job: Job, name: str, default: bool) -> bool:
    """Read a payload flag. A payload cannot turn a safety check off."""
    payload = job.payload or {}
    if name not in payload:
        return default
    value = bool(payload[name])
    if default and not value:
        return True
    return value


def _consent_granted(session: Session, case_id: UUID) -> bool:
    owner = session.scalar(
        select(Member).where(Member.case_id == case_id, Member.role == MemberRole.owner)
    )
    if owner is None:
        return False
    consent = owner.consent or {}
    if consent.get("status") == "revoked" or consent.get("granted") is False:
        return False
    return consent.get("status") == "granted" or consent.get("granted") is True


def _reason_gone(session: Session, job: Job) -> bool:
    reason = (job.payload or {}).get("reason") or {"type": "always"}
    kind = str(reason.get("type") or "always")
    if kind == "always":
        return False
    if kind == "awaiting_reply":
        since = datetime.fromisoformat(str(reason["since"]))
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        found = session.scalar(
            select(Commitment.id).where(
                Commitment.account_id == UUID(str(reason["account_id"])),
                Commitment.created_at >= since,
            )
        )
        return found is not None
    if kind == "refund_outstanding":
        item = session.get(MoneyItem, UUID(str(reason["money_item_id"])))
        return item is not None and item.status is MoneyItemStatus.received
    return True


def _plan_current(session: Session, job: Job) -> str | None:
    payload = job.payload or {}
    if "plan_id" not in payload:
        return None
    plan = session.get(Plan, UUID(str(payload["plan_id"])))
    if plan is None:
        return "plan_stale"
    version = int(payload.get("plan_version", -1))
    if plan.version != version or plan.hash != payload.get("plan_hash"):
        return "plan_stale"
    current = latest_plan(session, plan.account_id)
    if current is None or current.id != plan.id:
        return "plan_stale"
    return None


def _approval_valid(session: Session, job: Job) -> bool:
    payload = job.payload or {}
    approval_id = payload.get("approval_id")
    if not approval_id:
        return False
    approval = session.get(Approval, UUID(str(approval_id)))
    if approval is None or approval.status is not ApprovalStatus.approved:
        return False
    plan = session.get(Plan, approval.plan_id)
    if plan is None or plan.status is not PlanStatus.approved:
        return False
    return (
        approval.plan_version == plan.version
        and approval.plan_hash == plan.hash
        and str(payload.get("plan_hash")) == plan.hash
        and int(payload.get("plan_version", -1)) == plan.version
    )


def preflight(session: Session, job: Job, *, wall: datetime | None = None) -> PreflightResult:
    """Re-check control, consent, mailbox, plan, approval and reason. Cancel when any fail."""
    if job.status not in {JobStatus.pending, JobStatus.running}:
        return PreflightResult(False, "not_runnable")
    case = session.get(Case, job.case_id)
    if case is None:
        cancel_job(job, "case_missing")
        return PreflightResult(False, "case_missing")
    moment = wall or datetime.now(UTC)
    outbound = _flag(job, "outbound", job.kind in _OUTBOUND_KINDS)
    touches_family = _flag(job, "touches_family", job.kind in _FAMILY_KINDS)
    deadline_notice = _flag(job, "deadline_notice", False)
    routine = _flag(job, "routine", False)
    action = (job.payload or {}).get("action")
    decision = decide(
        case,
        job_kind=job.kind,
        outbound=outbound,
        touches_family=touches_family,
        deadline_notice=deadline_notice,
        action=str(action) if action else None,
        routine=routine,
        at=case_now(case, moment),
    )
    reason = ""
    if decision.effect == "deny":
        reason = decision.reason
    elif decision.effect == "ask" and job.kind == "followup":
        _ask_for_followup(session, case, job)
        session.flush()
        return PreflightResult(False, "approval_required")
    elif not _consent_granted(session, case.id):
        reason = "consent_revoked"
    elif _flag(job, "requires_mailbox", job.kind in _MAILBOX_KINDS) and (
        case.monitoring is not Monitoring.ok
    ):
        reason = "mailbox_unhealthy"
    else:
        stale = _plan_current(session, job)
        if stale:
            reason = stale
        elif job.kind in _NEEDS_APPROVAL and not _approval_valid(session, job):
            reason = "approval_invalid"
        elif _reason_gone(session, job):
            reason = "reason_gone"
    if reason:
        cancel_job(job, reason)
        session.flush()
        return PreflightResult(False, reason)
    return PreflightResult(True, "")
