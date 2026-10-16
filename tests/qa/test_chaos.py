"""Chaos on isolated rows: crash after send, consent, mailbox health, restart."""

import contextlib
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.jobs import enqueue, lease_due, preflight
from app.engine.plans import approve, revise_plan
from app.fakes.mailbox import FakeMailbox
from app.mail.health import MailboxWatch, apply_mailbox_health
from app.mail.outbound import execute_send_request, reconcile_action
from app.models import ActionStatus, JobStatus, Monitoring
from tests.engine.support import make_account, make_case, make_owner, make_provider
from tests.mail.support import account_by_ref, email_action, malik

APPROVED = "bereavement@northline.example"
NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class _KillOnce(FakeMailbox):
    """The provider accepts the message, then the worker dies before the row is saved."""

    def __init__(self) -> None:
        super().__init__()
        self.killed = False

    async def send(self, request):
        record = await super().send(request)
        if not self.killed:
            self.killed = True
            raise RuntimeError("worker killed after the provider accepted the send")
        return record


def _send_job(db_session, case):
    owner = make_owner(db_session, case)
    provider = make_provider(db_session)
    account = make_account(db_session, case, provider)
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="notify",
        conditions=[],
        documents=[],
        recipient=APPROVED,
    )
    approval = approve(
        db_session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=owner.id,
    )
    return owner, enqueue(
        db_session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=NOW - timedelta(minutes=1),
        idem_key=f"send:{case.ref}",
        payload={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "plan_hash": plan.hash,
            "approval_id": str(approval.id),
            "action": "notify",
            "outbound": True,
            "reason": {"type": "always"},
        },
    )


@pytest.mark.db
@pytest.mark.asyncio
async def test_worker_killed_after_send_reconciles_without_a_second_copy(db_session):
    """A send that landed, then a dead worker, becomes uncertain and reconciles once."""
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    mailbox = _KillOnce()
    action = email_action(db_session, case, account, idem_key="qa:kill:4417", action_key="k1")
    with contextlib.suppress(RuntimeError):
        await execute_send_request(db_session, action, mailbox=mailbox, bus=None)
    if action.status is ActionStatus.pending:
        with contextlib.suppress(RuntimeError):
            await execute_send_request(db_session, action, mailbox=mailbox, bus=None)
    else:
        await reconcile_action(db_session, action, mailbox)
    assert len(mailbox.sent) == 1
    assert action.status is ActionStatus.reconciled


@pytest.mark.db
def test_revoked_consent_blocks_a_queued_send(db_session):
    case = make_case(db_session)
    owner, job = _send_job(db_session, case)
    owner.consent = {"status": "revoked"}
    db_session.flush()
    result = preflight(db_session, job, wall=NOW)
    assert result.ok is False
    assert result.reason == "consent_revoked"
    assert job.status is JobStatus.cancelled


@pytest.mark.db
def test_expired_mailbox_token_interrupts_monitoring_and_blocks_the_send(db_session):
    case = make_case(db_session)
    _owner, job = _send_job(db_session, case)
    reason = apply_mailbox_health(
        db_session,
        case,
        _Bus(),
        MailboxWatch(last_poll_at=NOW, token_valid=False),
        now=NOW,
    )
    assert reason == "token_invalid"
    assert case.monitoring is Monitoring.interrupted
    result = preflight(db_session, job, wall=NOW)
    assert result.ok is False
    assert result.reason == "mailbox_unhealthy"
    assert job.status is JobStatus.cancelled


@pytest.mark.db
def test_expired_lease_is_retaken_and_the_case_row_remains(db_session):
    case = make_case(db_session)
    job = enqueue(
        db_session,
        case_id=case.id,
        kind="health_check",
        run_at_case_time=NOW - timedelta(minutes=1),
        idem_key=f"health:{case.ref}",
    )
    job.status = JobStatus.running
    job.lease_until = datetime.now(UTC) - timedelta(seconds=30)
    db_session.flush()
    leased = lease_due(db_session)
    assert job.id in {item.id for item in leased}
    assert db_session.get(type(case), case.id) is not None
    assert case.ref.startswith("AW-")


class _Bus:
    def publish(self, session, case_id, kind, payload, *, actor):
        del session, case_id, kind, payload, actor
