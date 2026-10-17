"""Durable job runner: lease due jobs, preflight, dispatch by kind."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.contracts import JOB_KINDS
from app.engine.jobs import (
    LEASE_SECONDS,
    case_now,
    complete_job,
    fail_job,
    lease_due,
    preflight,
)
from app.models import Case, Job, JobStatus

logger = logging.getLogger(__name__)

PARK_SECONDS = 24 * 3600


@dataclass
class RunContext:
    """What an executor may use. Built once per worker from settings; no secrets in logs."""

    settings: Any
    mailbox: Any | None = None  # app.contracts.Mailbox for the family/case mailbox
    ai: Any | None = None  # app.contracts.AIClient
    notify: Callable[[str], Awaitable[bool]] | None = None  # tell the case owner in chat
    # Ask the case owner a question with buttons: (text, [(button_id, label), ...]).
    ask: Callable[[str, list[tuple[str, str]]], Awaitable[bool]] | None = None
    extras: dict[str, Any] = field(default_factory=dict)


Executor = Callable[[Session, Job, RunContext], Awaitable[None]]
EXECUTORS: dict[str, Executor] = {}
SessionFactory = Callable[[], AbstractContextManager[Session]]


def register_executor(kind: str, fn: Executor) -> None:
    """Executors raise on failure; the runner records fail_job and retries."""
    EXECUTORS[kind] = fn


async def _health_check(session: Session, job: Job, ctx: RunContext) -> None:
    """Preflight already re-checked the case; a passing check needs no further work."""
    del session, job, ctx


def _park(session: Session, job: Job, wall: datetime) -> None:
    """Wait for the family: keep the job pending a day later and do not burn an attempt."""
    case = session.get(Case, job.case_id)
    job.status = JobStatus.pending
    job.lease_until = None
    job.attempts = max(0, job.attempts - 1)
    if case is not None:
        job.run_at_case_time = case_now(case, wall) + timedelta(seconds=PARK_SECONDS)


async def _ask_family_once(session: Session, job: Job, ctx: RunContext) -> None:
    """Put the open follow-up decision in front of the family once, as buttons in chat."""
    from sqlalchemy import select

    from app.models import Decision, DecisionStatus

    decision = session.scalar(
        select(Decision).where(
            Decision.case_id == job.case_id,
            Decision.kind == "followup",
            Decision.status == DecisionStatus.open,
        )
    )
    if decision is None or (decision.payload or {}).get("asked") or ctx.ask is None:
        return
    label = str(((job.payload or {}).get("reason") or {}).get("label") or "this account")
    sent = await ctx.ask(
        f"No reply yet about {label}. Shall I send the follow-up you already approved?",
        [(f"fu:{decision.id}:send", "Send follow-up"), (f"fu:{decision.id}:not_now", "Not now")],
    )
    if sent:
        decision.payload = {**(decision.payload or {}), "asked": True}


async def _run_one(session: Session, job: Job, ctx: RunContext, wall: datetime) -> bool:
    """Run one leased job. Returns True when an executor completed it."""
    result = preflight(session, job, wall=wall)
    if not result.ok:
        if job.status is JobStatus.running:
            _park(session, job, wall)  # approval_required: the family has been asked
            if job.kind == "followup":
                await _ask_family_once(session, job, ctx)
        return False
    if job.kind not in JOB_KINDS:
        job.status = JobStatus.failed
        job.lease_until = None
        job.last_error = "unknown_kind"
        return False
    executor = EXECUTORS.get(job.kind)
    if executor is None:
        fail_job(session, job, "no_executor", wall=wall)
        return False
    await executor(session, job, ctx)
    complete_job(job)
    return True


async def run_due_jobs(session_factory: SessionFactory, ctx: RunContext, *, wall: datetime) -> int:
    """Lease and run due jobs of every kind. Returns how many completed.

    A failure records only the exception class name, then retries with backoff.
    """
    if wall.tzinfo is None:
        raise ValueError("run_due_jobs requires a timezone-aware wall time")
    with session_factory() as session:
        leased = [j.id for j in lease_due(session, wall=wall, lease_seconds=LEASE_SECONDS)]
        session.commit()
    done = 0
    for job_id in leased:
        done += await _run_leased(session_factory, ctx, job_id, wall)
    return done


async def _run_leased(session_factory: SessionFactory, ctx: RunContext, job_id: UUID, wall) -> int:
    try:
        with session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status is not JobStatus.running:
                return 0
            ok = await _run_one(session, job, ctx, wall)
            session.commit()
            return int(ok)
    except Exception as exc:
        name = type(exc).__name__
        logger.info("job failed", extra={"kind": "job.failed", "job_id": str(job_id)})
        with session_factory() as session:
            job = session.get(Job, job_id)
            if job is not None and job.status in {JobStatus.running, JobStatus.pending}:
                fail_job(session, job, name, wall=wall)
            session.commit()
        return 0


def now_utc() -> datetime:
    """Wall clock for the supervisor."""
    return datetime.now(UTC)


register_executor("health_check", _health_check)
