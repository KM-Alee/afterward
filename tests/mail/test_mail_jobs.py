"""Mail executors: poll to outcome, monitoring, approval and recipient denial, reconcile."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.ai.schemas import CommitmentOut, Fact, ReplyOut
from app.contracts import SendRequest, SqlEventBus
from app.demo.provider_variants import send_provider_reply
from app.engine.jobs import enqueue
from app.engine.runner import RunContext
from app.fakes.mailbox import FakeMailbox
from app.mail.errors import DeliveryUncertain, MailError
from app.mail.jobs import (
    inbox_poll,
    reconcile_action,
    register_mail_executors,
    send_request,
)
from app.mail.outbound import execute_send_request
from app.models import (
    Action,
    ActionStatus,
    Approval,
    ApprovalStatus,
    Job,
    Member,
    Monitoring,
    OutcomeCheck,
)
from tests.mail.support import FAMILY, PROVIDERS, account_by_ref, approved_plan, email_action, malik


class RecordedAI:
    async def structured(self, role, schema, messages, images=None):
        quote = "Voicemail will be reset during migration."
        return ReplyOut(
            commitments=[
                CommitmentOut(
                    account_hint="line ending 4417",
                    action="transfer",
                    status="completed",
                    negated=False,
                    conditions_or_requirements=[],
                    facts=[Fact(key="voicemail_preserved", value="false", evidence_quote=quote)],
                    scope="this_service",
                    effective_date=None,
                    evidence_quote="Line transferred to Mrs Malik on a new 24-month plan.",
                    interpretation="clear",
                )
            ],
            asks_for_documents=[],
            is_marketing_to_deceased=False,
        )


def ctx_for(mailbox, ai=None) -> RunContext:
    return RunContext(settings=SimpleNamespace(family_mailbox=FAMILY), mailbox=mailbox, ai=ai)


def make_job(session, case, kind, payload, key) -> Job:
    from datetime import UTC, datetime

    return enqueue(
        session,
        case_id=case.id,
        kind=kind,
        run_at_case_time=datetime.now(UTC),
        idem_key=key,
        payload=payload,
    )


def approve(session, case, plan) -> dict:
    owner = session.scalar(select(Member).where(Member.case_id == case.id))
    approval = Approval(
        case_id=case.id,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_hash=plan.hash,
        member_id=owner.id,
        status=ApprovalStatus.approved,
    )
    session.add(approval)
    session.flush()
    return {
        "approval_id": str(approval.id),
        "plan_id": str(plan.id),
        "plan_version": plan.version,
        "plan_hash": plan.hash,
    }


class OnceUncertain(FakeMailbox):
    """The first send raises DeliveryUncertain; `left` says whether it actually left."""

    def __init__(self, left: bool) -> None:
        super().__init__()
        self.left = left
        self.calls = 0

    async def send(self, request: SendRequest):
        self.calls += 1
        if self.calls == 1:
            if self.left:
                await super().send(request)
            raise DeliveryUncertain("timeout")
        return await super().send(request)


def test_register_installs_the_three_kinds():
    seen: dict[str, object] = {}
    register_mail_executors(lambda kind, fn: seen.setdefault(kind, fn))
    assert set(seen) == {"inbox_poll", "send_request", "reconcile_action"}


@pytest.mark.db
@pytest.mark.asyncio
async def test_poll_ingests_checks_outcome_and_sets_monitoring_only_after_poll(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    approved_plan(db_session, case, account)
    family = FakeMailbox()
    action = email_action(db_session, case, account, idem_key="send:p1", action_key="1")
    await execute_send_request(db_session, action, mailbox=family, bus=SqlEventBus())
    await send_provider_reply(
        providers=FakeMailbox(),
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=family.sent[0].thread_id,
        in_reply_to=family.sent[0].rfc_message_id,
        variant="nl_contradictory",
    )
    case.monitoring = Monitoring.interrupted
    job = make_job(db_session, case, "inbox_poll", {"seq": 0}, "inbox_poll:t1:0")
    assert case.monitoring is Monitoring.interrupted  # nothing flips it before a poll

    await inbox_poll(db_session, job, ctx_for(family, RecordedAI()))

    assert case.monitoring is Monitoring.ok
    outcome = db_session.scalar(select(OutcomeCheck))
    assert outcome is not None and outcome.verdict == "needs_decision"
    nxt = db_session.scalar(select(Job).where(Job.idem_key == f"inbox_poll:{case.id}:1"))
    assert nxt is not None and nxt.payload["cursor"]["history_id"]
    # A second run of the same job queues the same next job and ingests nothing twice.
    await inbox_poll(db_session, job, ctx_for(family, RecordedAI()))
    jobs = list(db_session.scalars(select(Job).where(Job.kind == "inbox_poll")))
    assert len([j for j in jobs if j.idem_key.endswith(":1")]) == 1
    assert len(list(db_session.scalars(select(OutcomeCheck)))) == 1


@pytest.mark.db
@pytest.mark.asyncio
async def test_failed_poll_interrupts_monitoring_and_still_queues_the_next(db_session):
    case = malik(db_session)

    class Broken(FakeMailbox):
        async def poll(self, mailbox, cursor):
            raise RuntimeError("boom")

    job = make_job(db_session, case, "inbox_poll", {"seq": 4}, "inbox_poll:t2:4")
    await inbox_poll(db_session, job, ctx_for(Broken()))
    assert case.monitoring is Monitoring.interrupted
    assert db_session.scalar(select(Job).where(Job.idem_key == f"inbox_poll:{case.id}:5"))


@pytest.mark.db
@pytest.mark.asyncio
async def test_approved_reply_without_an_ai_client_fails_loudly(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    approved_plan(db_session, case, account)
    family = FakeMailbox()
    action = email_action(db_session, case, account, idem_key="send:p2", action_key="2")
    await execute_send_request(db_session, action, mailbox=family, bus=None)
    await send_provider_reply(
        providers=FakeMailbox(),
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=family.sent[0].thread_id,
        variant="nl_ack",
    )
    job = make_job(db_session, case, "inbox_poll", {"seq": 0}, "inbox_poll:t3:0")
    await inbox_poll(db_session, job, ctx_for(family, None))
    assert case.monitoring is Monitoring.interrupted  # never reported healthy
    assert db_session.scalar(select(OutcomeCheck)) is None


@pytest.mark.db
@pytest.mark.asyncio
async def test_send_request_denied_without_a_current_approval(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    plan = approved_plan(db_session, case, account)
    action = email_action(db_session, case, account, idem_key="send:d1", action_key="d1")
    family = FakeMailbox()
    payload = {"action_id": str(action.id), "plan_id": str(plan.id)}
    job = make_job(db_session, case, "send_request", payload, "send_request:d1")
    with pytest.raises(MailError):
        await send_request(db_session, job, ctx_for(family))
    assert family.sent == [] and action.status is ActionStatus.pending

    stale = {**approve(db_session, case, plan), "action_id": str(action.id), "plan_hash": "00"}
    job2 = make_job(db_session, case, "send_request", stale, "send_request:d1b")
    with pytest.raises(MailError):
        await send_request(db_session, job2, ctx_for(family))
    assert family.sent == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_send_request_refuses_an_unapproved_recipient(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    plan = approved_plan(db_session, case, account)
    action = email_action(db_session, case, account, idem_key="send:d2", action_key="d2")
    action.request = {**action.request, "to_addrs": ["attacker@evil.example"]}
    payload = {**approve(db_session, case, plan), "action_id": str(action.id)}
    job = make_job(db_session, case, "send_request", payload, "send_request:d2")
    family = FakeMailbox()
    with pytest.raises(MailError):
        await send_request(db_session, job, ctx_for(family))
    assert family.sent == []
    assert action.request["blocked"] == "recipient_not_approved"


@pytest.mark.db
@pytest.mark.asyncio
async def test_send_request_sends_with_approval_and_followup_payload_works(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    plan = approved_plan(db_session, case, account)
    action = email_action(db_session, case, account, idem_key="send:ok", action_key="ok")
    family = FakeMailbox()
    carry = approve(db_session, case, plan)
    job = make_job(
        db_session, case, "send_request", {**carry, "action_id": str(action.id)}, "send_request:ok"
    )
    await send_request(db_session, job, ctx_for(family))
    assert action.status is ActionStatus.sent and len(family.sent) == 1

    fu = make_job(
        db_session,
        case,
        "send_request",
        {**carry, "followup": True, "followup_job_id": "f-1", "account_id": str(account.id)},
        "send:followup:1",
    )
    await send_request(db_session, fu, ctx_for(family))
    assert len(family.sent) == 2
    assert family.sent[1].thread_id == family.sent[0].thread_id
    follow = db_session.scalar(select(Action).where(Action.idem_key == "followup:f-1"))
    assert follow is not None and follow.status is ActionStatus.sent
    await send_request(db_session, fu, ctx_for(family))
    assert len(family.sent) == 2


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("left", [True, False])
async def test_uncertain_send_queues_reconcile_without_double_sending(db_session, left):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    plan = approved_plan(db_session, case, account)
    action = email_action(db_session, case, account, idem_key=f"send:u{left}", action_key="u")
    family = OnceUncertain(left=left)
    carry = approve(db_session, case, plan)
    job = make_job(
        db_session, case, "send_request", {**carry, "action_id": str(action.id)}, f"sr:u{left}"
    )
    await send_request(db_session, job, ctx_for(family))
    assert action.status is ActionStatus.uncertain
    rec = db_session.scalar(select(Job).where(Job.kind == "reconcile_action"))
    assert rec is not None

    await reconcile_action(db_session, rec, ctx_for(family))
    assert len(family.sent) == 1  # found in Sent, or sent once more because it never left
    assert action.status in {ActionStatus.reconciled, ActionStatus.sent}
    assert (action.status is ActionStatus.reconciled) is left


@pytest.mark.db
@pytest.mark.asyncio
async def test_reconcile_never_resends_when_the_approval_is_gone(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    plan = approved_plan(db_session, case, account)
    action = email_action(db_session, case, account, idem_key="send:g", action_key="g")
    action.status = ActionStatus.uncertain
    action.request = {**action.request, "footer_ref": "AW-1042-g", "mailbox": FAMILY}
    family = FakeMailbox()
    job = make_job(
        db_session,
        case,
        "reconcile_action",
        {"action_id": str(action.id), "plan_id": str(plan.id)},
        "reconcile:g",
    )
    await reconcile_action(db_session, job, ctx_for(family))
    assert family.sent == [] and action.status is ActionStatus.uncertain
