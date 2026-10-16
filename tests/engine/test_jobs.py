"""Leases, idempotency, case clock, business days and preflight denials."""

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.contracts import ContractError
from app.engine.jobs import (
    add_business_days,
    case_now,
    enqueue,
    fail_job,
    is_due,
    lease_due,
    preflight,
    schedule_followup,
)
from app.engine.plans import approve, revise_plan
from app.models import (
    Autopilot,
    Commitment,
    Interpretation,
    JobStatus,
    Message,
    MessageDirection,
    Monitoring,
    PlanAction,
)
from tests.engine.support import make_account, make_case, make_owner, make_provider

NOW = datetime(2026, 3, 6, 9, tzinfo=UTC)


class _Clock:
    def __init__(self, offset: int) -> None:
        self.clock_offset_s = offset


def test_case_clock_and_business_days():
    friday = datetime(2026, 3, 6, 23, tzinfo=UTC)
    assert case_now(_Clock(0), friday) == friday
    assert case_now(_Clock(7200), friday) == friday + timedelta(hours=2)
    with pytest.raises(ValueError):
        case_now(_Clock(0), datetime(2026, 3, 6))
    monday = datetime(2026, 3, 9, 9, tzinfo=UTC)
    assert add_business_days(NOW, 1) == monday
    saturday = case_now(_Clock(15 * 3600), NOW)
    assert saturday.weekday() == 5
    assert add_business_days(saturday, 1) == datetime(2026, 3, 9, 0, tzinfo=UTC)


def test_is_due_uses_case_time_and_expired_leases():
    case = _Clock(3600)
    job = type("Job", (), {})()
    job.status = JobStatus.pending
    job.run_at_case_time = NOW + timedelta(minutes=30)
    job.lease_until = None
    assert is_due(job, case, NOW) is True
    assert is_due(job, _Clock(0), NOW) is False
    job.status = JobStatus.running
    job.lease_until = NOW - timedelta(seconds=1)
    assert is_due(job, _Clock(0), NOW) is True
    job.lease_until = NOW + timedelta(seconds=30)
    assert is_due(job, _Clock(0), NOW) is False


@pytest.mark.db
def test_enqueue_is_idempotent_and_unknown_kinds_are_refused(db_session):
    case = make_case(db_session)
    when = datetime.now(UTC) - timedelta(minutes=1)
    first = enqueue(
        db_session,
        case_id=case.id,
        kind="inbox_poll",
        run_at_case_time=when,
        idem_key="poll:once",
        payload={"n": 1},
    )
    second = enqueue(
        db_session,
        case_id=case.id,
        kind="inbox_poll",
        run_at_case_time=when,
        idem_key="poll:once",
        payload={"n": 2},
    )
    assert first.id == second.id
    assert first.payload["n"] == 1
    with pytest.raises(ContractError):
        enqueue(
            db_session,
            case_id=case.id,
            kind="not-a-job",
            run_at_case_time=when,
            idem_key="nope",
        )


@pytest.mark.db
def test_lease_uses_skip_locked(db_engine):
    with Session(db_engine) as setup:
        case = make_case(setup)
        enqueue(
            setup,
            case_id=case.id,
            kind="health_check",
            run_at_case_time=datetime.now(UTC) - timedelta(minutes=1),
            idem_key="health:race",
        )
        setup.commit()
        case_id = case.id
    with db_engine.connect() as first_conn:
        first_tx = first_conn.begin()
        first = Session(bind=first_conn)
        leased = lease_due(first)
        assert any(job.case_id == case_id for job in leased)
        with db_engine.connect() as second_conn:
            second_tx = second_conn.begin()
            second = Session(bind=second_conn)
            again = lease_due(second)
            assert all(job.case_id != case_id for job in again)
            second_tx.rollback()
        first_tx.rollback()


@pytest.mark.db
def test_idempotency_race_keeps_one_row(db_engine):
    with Session(db_engine) as setup:
        case = make_case(setup)
        setup.commit()
        case_id = case.id
    started = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with Session(db_engine) as session:
            enqueue(
                session,
                case_id=case_id,
                kind="digest",
                run_at_case_time=datetime.now(UTC),
                idem_key="digest:race",
            )
            started.set()
            release.wait(timeout=5)
            session.commit()

    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(timeout=5)
    releaser = threading.Thread(target=lambda: (time.sleep(0.3), release.set()))
    releaser.start()
    with Session(db_engine) as session:
        winner = enqueue(
            session,
            case_id=case_id,
            kind="digest",
            run_at_case_time=datetime.now(UTC),
            idem_key="digest:race",
        )
        session.commit()
        assert winner.idem_key == "digest:race"
    thread.join(timeout=5)
    releaser.join(timeout=5)
    with Session(db_engine) as session:
        rows = session.query(type(winner)).filter_by(idem_key="digest:race").all()
        assert len(rows) == 1


@pytest.mark.db
def test_preflight_cancels_on_control_consent_mailbox_plan_approval_and_reason(db_session):
    case = make_case(db_session)
    owner = make_owner(db_session, case)
    account = make_account(db_session, case, make_provider(db_session))
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="notify",
        conditions=[],
        documents=[],
        recipient="bereavement@northline.example",
    )
    approval = approve(
        db_session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=owner.id,
    )
    when = datetime.now(UTC) - timedelta(minutes=1)
    payload = {
        "plan_id": str(plan.id),
        "plan_version": plan.version,
        "plan_hash": plan.hash,
        "approval_id": str(approval.id),
        "action": "notify",
        "outbound": True,
        "reason": {"type": "always"},
    }
    ok = enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=when,
        idem_key="send:ok",
        payload=payload,
    )
    assert preflight(db_session, ok).ok is True
    stopped = enqueue(
        db_session,
        case_id=case.id,
        kind="inbox_poll",
        run_at_case_time=when,
        idem_key="poll:stop",
    )
    case.control = case.control.__class__.stopped
    assert preflight(db_session, stopped).reason == "stopped"
    case.control = case.control.__class__.active
    owner.consent = {"status": "revoked"}
    db_session.flush()
    revoked = enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=when,
        idem_key="send:revoked",
        payload=payload,
    )
    assert preflight(db_session, revoked).reason == "consent_revoked"
    owner.consent = {"status": "granted"}
    case.monitoring = Monitoring.interrupted
    db_session.flush()
    unhealthy = enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=when,
        idem_key="send:mailbox",
        payload=payload,
    )
    assert preflight(db_session, unhealthy).reason == "mailbox_unhealthy"
    case.monitoring = Monitoring.ok
    stale = enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=when,
        idem_key="send:stale",
        payload={**payload, "plan_hash": "f" * 64},
    )
    assert preflight(db_session, stale).reason == "plan_stale"
    missing_approval = enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=when,
        idem_key="send:no-approval",
        payload={key: value for key, value in payload.items() if key != "approval_id"},
    )
    assert preflight(db_session, missing_approval).reason == "approval_invalid"
    case.autopilot = Autopilot.steady
    follow = schedule_followup(
        db_session,
        case=case,
        account_id=account.id,
        plan=plan,
        approval_id=approval.id,
        sent_at=datetime(2026, 3, 6, 9, tzinfo=UTC),
        window_bd=5,
    )
    assert follow.run_at_case_time == datetime(2026, 3, 13, 9, tzinfo=UTC)
    message = Message(
        case_id=case.id,
        direction=MessageDirection.inbound,
        from_addr="bereavement@northline.example",
        latest_text="We received your request.",
        received_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.flush()
    db_session.add(
        Commitment(
            case_id=case.id,
            message_id=message.id,
            account_id=account.id,
            action=PlanAction.notify,
            status="acknowledged",
            scope="this_service",
            evidence_quote="We received your request.",
            quote_verified=True,
            interpretation=Interpretation.clear,
        )
    )
    db_session.flush()
    assert preflight(db_session, follow).reason == "reason_gone"


@pytest.mark.db
def test_fail_job_retries_then_stops(db_session):
    case = make_case(db_session)
    job = enqueue(
        db_session,
        case_id=case.id,
        kind="inbox_poll",
        run_at_case_time=datetime.now(UTC),
        idem_key="poll:retry",
    )
    job.status = JobStatus.running
    job.attempts = 1
    wall = datetime(2026, 4, 2, tzinfo=UTC)
    fail_job(db_session, job, "timeout", wall=wall)
    assert job.status is JobStatus.pending
    assert job.attempts == 1
    job.status = JobStatus.running
    job.attempts = 3
    fail_job(db_session, job, "timeout", wall=wall)
    assert job.status is JobStatus.failed
