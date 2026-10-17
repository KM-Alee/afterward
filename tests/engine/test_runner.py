"""Runner: due/not-due, preflight denials, retries, unknown kinds, engine executors."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import clock as clock_module
from app.engine import executors  # noqa: F401  (registers the engine kinds)
from app.engine.clock import advance_case_clock
from app.engine.errors import EngineError
from app.engine.jobs import MAX_ATTEMPTS, enqueue
from app.engine.runner import EXECUTORS, RunContext, register_executor, run_due_jobs
from app.models import CaseControl, Job, JobStatus
from tests.engine.support import make_case, make_owner


@pytest.fixture
def factory(db_session):
    @contextmanager
    def make():
        yield db_session

    return make


@pytest.fixture
def restore_executors():
    saved = dict(EXECUTORS)
    yield
    EXECUTORS.clear()
    EXECUTORS.update(saved)


def _job(session, case, kind="inbox_poll", *, minutes=-1, key=None, **payload):
    return enqueue(
        session,
        case_id=case.id,
        kind=kind,
        run_at_case_time=datetime.now(UTC) + timedelta(minutes=minutes),
        idem_key=key or f"{kind}:{case.id}:{minutes}",
        payload=payload,
    )


def _ctx():
    return RunContext(settings=None)


def _calls(kind):
    calls = []

    async def run(session, job, ctx):
        calls.append(job.id)

    register_executor(kind, run)
    return calls


@pytest.mark.db
async def test_due_job_runs_and_future_job_waits(db_session, factory, restore_executors):
    case = make_case(db_session)
    make_owner(db_session, case)
    calls = _calls("inbox_poll")
    due = _job(db_session, case, minutes=-1, key=f"due:{case.id}")
    later = _job(db_session, case, minutes=60, key=f"later:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(due)
    db_session.refresh(later)
    assert due.status is JobStatus.succeeded and due.id in calls
    assert later.status is JobStatus.pending and later.id not in calls


@pytest.mark.db
async def test_case_clock_makes_a_future_job_due(db_session, factory, restore_executors):
    case = make_case(db_session)
    make_owner(db_session, case)
    calls = _calls("inbox_poll")
    job = _job(db_session, case, minutes=60 * 24 * 14, key=f"clock:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    assert job.id not in calls
    advance_case_clock(db_session, case.id, 15 * 24 * 3600)
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.succeeded and job.id in calls


@pytest.mark.db
async def test_preflight_denial_cancels_without_running(db_session, factory, restore_executors):
    case = make_case(db_session, control=CaseControl.stopped)
    make_owner(db_session, case)
    calls = _calls("inbox_poll")
    job = _job(db_session, case, key=f"stop:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.cancelled and job.last_error == "stopped"
    assert job.id not in calls


@pytest.mark.db
async def test_revoked_consent_cancels(db_session, factory, restore_executors):
    case = make_case(db_session)
    make_owner(db_session, case, granted=False)
    calls = _calls("inbox_poll")
    job = _job(db_session, case, key=f"consent:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.cancelled and job.last_error == "consent_revoked"
    assert job.id not in calls


@pytest.mark.db
async def test_failure_retries_with_class_name_only_then_fails(
    db_session, factory, restore_executors
):
    case = make_case(db_session)
    make_owner(db_session, case)

    async def boom(session, job, ctx):
        raise KeyError("secret body text")

    register_executor("inbox_poll", boom)
    job = _job(db_session, case, key=f"boom:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.pending
    assert job.last_error == "KeyError" and "secret" not in job.last_error
    assert job.run_at_case_time > datetime.now(UTC)
    for _ in range(MAX_ATTEMPTS):
        job.run_at_case_time = datetime.now(UTC) - timedelta(minutes=1)
        db_session.commit()
        await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
        db_session.refresh(job)
    assert job.status is JobStatus.failed
    assert job.attempts == MAX_ATTEMPTS


@pytest.mark.db
async def test_known_kind_without_executor_fails_closed(db_session, factory, restore_executors):
    case = make_case(db_session)
    make_owner(db_session, case)
    EXECUTORS.pop("reconcile_action", None)
    job = _job(db_session, case, "reconcile_action", key=f"noexec:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.pending and job.last_error == "no_executor"


@pytest.mark.db
async def test_unknown_kind_is_failed_not_run(db_session, factory, restore_executors):
    case = make_case(db_session)
    make_owner(db_session, case)
    job = Job(
        case_id=case.id,
        kind="wire_money",
        run_at_case_time=datetime.now(UTC) - timedelta(minutes=1),
        idem_key=f"unknown:{case.id}",
        payload={},
    )
    db_session.add(job)
    db_session.commit()
    calls = _calls("wire_money")
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.failed and job.last_error == "unknown_kind"
    assert not calls


@pytest.mark.db
async def test_health_check_is_just_an_executor(db_session, factory):
    case = make_case(db_session)
    make_owner(db_session, case)
    job = _job(db_session, case, "health_check", key=f"health:{case.id}")
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.succeeded


@pytest.mark.db
async def test_gentle_followup_asks_the_family_and_parks(db_session, factory):
    from sqlalchemy import select

    from app.models import Decision

    case = make_case(db_session)
    make_owner(db_session, case)
    job = _job(db_session, case, "followup", key=f"fu:{case.id}", outbound=True)
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.pending
    assert job.run_at_case_time > datetime.now(UTC) + timedelta(hours=12)
    assert job.attempts == 0
    asked = db_session.scalars(
        select(Decision).where(Decision.case_id == case.id, Decision.kind == "followup")
    ).all()
    assert len(asked) == 1
    assert (
        db_session.scalar(select(Job).where(Job.case_id == case.id, Job.kind == "send_request"))
        is None
    )


@pytest.mark.db
async def test_followup_without_approval_never_queues_a_send(db_session, factory):
    from sqlalchemy import select

    from app.models import Autopilot

    case = make_case(db_session, autopilot=Autopilot.steady)
    make_owner(db_session, case)
    job = _job(db_session, case, "followup", key=f"fu2:{case.id}", outbound=True)
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.cancelled and job.last_error == "approval_invalid"
    assert (
        db_session.scalar(select(Job).where(Job.case_id == case.id, Job.kind == "send_request"))
        is None
    )


@pytest.mark.db
async def test_demo_followup_queues_send_after_steady_and_clock(db_session, factory):
    from sqlalchemy import select

    from app.engine.demo_case import ensure_demo_case
    from app.models import Autopilot, Case

    case_id = ensure_demo_case(db_session)
    again = ensure_demo_case(db_session)
    assert again == case_id
    case = db_session.get(Case, case_id)
    case.autopilot = Autopilot.steady
    followup = db_session.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "followup"))
    assert followup.run_at_case_time > datetime.now(UTC) + timedelta(days=13)
    advance_case_clock(db_session, case_id, 15 * 24 * 3600)
    db_session.commit()
    await run_due_jobs(factory, _ctx(), wall=datetime.now(UTC))
    db_session.refresh(followup)
    assert followup.status is JobStatus.succeeded
    send = db_session.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "send_request"))
    assert send is not None and send.payload["approval_id"] == followup.payload["approval_id"]
    assert send.payload["followup"] is True


@pytest.mark.db
async def test_refund_check_asks_then_reschedules_and_stops(db_session, factory):
    from decimal import Decimal

    from app.models import MoneyItem, MoneyItemStatus, MoneyKind
    from tests.engine.support import make_account

    case = make_case(db_session)
    make_owner(db_session, case)
    account = make_account(db_session, case)
    item = MoneyItem(
        case_id=case.id,
        account_id=account.id,
        kind=MoneyKind.refund,
        amount=Decimal("12.00"),
        status=MoneyItemStatus.refund_promised,
    )
    db_session.add(item)
    db_session.flush()
    told: list[str] = []

    async def notify(text: str) -> bool:
        told.append(text)
        return True

    ctx = RunContext(settings=None, notify=notify)
    job = _job(
        db_session,
        case,
        "refund_evidence_check",
        key=f"refund:{item.id}:n1",
        money_item_id=str(item.id),
        reason={"type": "refund_outstanding", "money_item_id": str(item.id)},
        requires_mailbox=False,
    )
    db_session.commit()
    await run_due_jobs(factory, ctx, wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.succeeded and len(told) == 1
    assert "arrived" in told[0] and "received" in told[0]
    nxt = db_session.scalar(select_next(case.id, f"refund_evidence:{item.id}:n2"))
    assert nxt is not None and nxt.payload["check_n"] == 2
    item.status = MoneyItemStatus.received
    db_session.commit()
    nxt.run_at_case_time = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    await run_due_jobs(factory, ctx, wall=datetime.now(UTC))
    db_session.refresh(nxt)
    assert nxt.status is JobStatus.cancelled and nxt.last_error == "reason_gone"
    assert len(told) == 1


def select_next(case_id, key):
    from sqlalchemy import select

    return select(Job).where(Job.case_id == case_id, Job.idem_key == key)


@pytest.mark.db
async def test_digest_uses_code_counts_and_reschedules(db_session, factory):
    case = make_case(db_session)
    make_owner(db_session, case)
    told: list[str] = []

    async def notify(text: str) -> bool:
        told.append(text)
        return True

    job = _job(
        db_session,
        case,
        "digest",
        key=f"digest:{case.id}:n1",
        touches_family=True,
    )
    db_session.commit()
    await run_due_jobs(factory, RunContext(settings=None, notify=notify), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.succeeded and "confirmed with written evidence" in told[0]
    assert db_session.scalar(select_next(case.id, f"digest:{case.id}:n2")) is not None


@pytest.mark.db
async def test_quiet_case_skips_digest(db_session, factory):
    case = make_case(
        db_session,
        control=CaseControl.quiet_until,
        quiet_until=datetime.now(UTC) + timedelta(days=2),
    )
    make_owner(db_session, case)
    job = _job(db_session, case, "digest", key=f"digestq:{case.id}", touches_family=True)
    db_session.commit()
    await run_due_jobs(factory, RunContext(settings=None), wall=datetime.now(UTC))
    db_session.refresh(job)
    assert job.status is JobStatus.cancelled and job.last_error == "quiet"


@pytest.mark.db
def test_clock_advance_is_demo_only_and_bounded(db_session):
    case = make_case(db_session)
    assert advance_case_clock(db_session, case.id, 3600) == 3600
    assert advance_case_clock(db_session, case.id, 3600) == 7200
    for bad in (0, -5, clock_module.MAX_ADVANCE_SECONDS + 1):
        with pytest.raises(EngineError):
            advance_case_clock(db_session, case.id, bad)
    real = make_case(db_session)
    real.is_demo = False
    db_session.flush()
    with pytest.raises(EngineError) as info:
        advance_case_clock(db_session, real.id, 3600)
    assert info.value.code == "clock_demo_only"
