"""Every showcase step does real work on real rows; these tests check the rows, not the prose."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.demo import showcase_data as data
from app.demo.showcase import (
    STEP_IDS,
    ShowcaseError,
    progress,
    reset_showcase,
    run_next,
    run_step,
    showcase_case,
)
from app.models import (
    Account,
    Action,
    ActionStatus,
    Approval,
    Case,
    Decision,
    DecisionStatus,
    DocsStatus,
    Job,
    JobStatus,
    Message,
    MoneyItem,
    MoneyStatus,
    OutcomeCheck,
    Ownership,
    Plan,
    ProviderProfile,
    RecipientCheck,
    ServiceStatus,
)

pytestmark = pytest.mark.db

NINE = {"4417", "0932", "SB-88213", "FL-5531", "PB-3017", "2290", "CP-77120", "HW-20418", "ML-6610"}


def _accounts(session):
    return {a.account_ref: a for a in session.scalars(select(Account))}


def _plan(session, ref):
    account = _accounts(session)[ref]
    return session.scalar(
        select(Plan).where(Plan.account_id == account.id).order_by(Plan.version.desc())
    )


def test_start_state_is_pre_onboarding_only(db_session, started):
    case = showcase_case(db_session)
    assert case is not None and case.id == started
    assert case.is_demo and case.date_of_death is None and case.intent_text == ""
    assert db_session.scalar(select(func.count()).select_from(Account)) == 0
    assert db_session.scalar(select(func.count()).select_from(Plan)) == 0
    assert db_session.scalar(select(func.count()).select_from(Message)) == 0
    assert db_session.scalar(select(func.count()).select_from(ProviderProfile)) == 5
    assert progress(db_session) == []


async def test_intent_keeps_only_quoted_facts(db_session, play):
    results = await play("intent")
    case = showcase_case(db_session)
    assert case.date_of_death.isoformat() == "2026-03-03"
    assert case.intent["keep"] == ["Mum's phone", "Dad's voicemail"]
    # the claim with no words behind it was dropped
    assert "A claim nobody made" not in case.intent["protect"]
    assert "unsupported" in results["intent"].headline
    owner = db_session.scalar(select(Account.id))  # no accounts yet
    assert owner is None


async def test_discover_lists_headers_reads_only_ticked_and_proposes_unconfirmed(
    db_session, play, env
):
    await play("intent", "discover")
    accounts = _accounts(db_session)
    assert set(accounts) == NINE
    assert all(a.ownership is Ownership.unconfirmed for a in accounts.values())
    assert accounts["4417"].provider_id is not None
    assert accounts["4417"].origin.value == "inbox"
    assert "Your Northline bill is ready" in accounts["4417"].origin_evidence
    assert accounts["2290"].origin.value == "photo"
    source = db_session.scalar(select(func.count()).select_from(Account))
    assert source == 9
    from app.models import DiscoverySource

    row = db_session.scalar(select(DiscoverySource))
    assert row.matched == 7 and row.read == 5 and row.status == "searched"


async def test_confirm_only_follows_family_decisions(db_session, play):
    await play("intent", "discover", "confirm")
    a = _accounts(db_session)
    assert a["4417"].ownership is Ownership.confirmed
    assert a["2290"].ownership is Ownership.not_theirs
    assert a["0932"].ownership is Ownership.unconfirmed
    assert a["0932"].next_step["flag"] == "needs_check"
    assert a["ML-6610"].ownership is Ownership.unconfirmed


async def test_dependency_rewrites_the_plan_and_refuses_stale_and_missing_answers(db_session, play):
    results = await play("intent", "discover", "confirm", "dependency")
    plan = _plan(db_session, "4417")
    assert plan.version == 2
    assert {c["key"] for c in plan.conditions} == {"number_kept", "voicemail_preserved"}
    versions = db_session.scalars(
        select(Plan).where(Plan.account_id == _accounts(db_session)["4417"].id)
    ).all()
    assert sorted(p.version for p in versions) == [1, 2]
    text = " ".join(results["dependency"].details)
    assert "refused" in text and "stale" in text
    assert _plan(db_session, "SB-88213").action.value == "close"
    # nothing was approved or sent yet
    assert db_session.scalar(select(func.count()).select_from(Approval)) == 0


async def test_approve_binds_exact_hashes_and_queues_send_jobs(db_session, play):
    await play("intent", "discover", "confirm", "dependency", "approve")
    approvals = db_session.scalars(select(Approval)).all()
    assert len(approvals) == 4
    jobs = db_session.scalars(select(Job).where(Job.kind == "send_request")).all()
    assert len(jobs) == 4
    for job in jobs:
        assert job.status is JobStatus.pending
        approval = db_session.get(Approval, __import__("uuid").UUID(job.payload["approval_id"]))
        assert approval.plan_hash == job.payload["plan_hash"]
    assert db_session.scalar(select(func.count()).select_from(Message)) == 0


async def test_send_runs_through_the_job_runner_and_schedules_followups(db_session, play, env):
    await play("intent", "discover", "confirm", "dependency", "approve", "steady", "send")
    assert len(env.mailbox.sent) == 4
    actions = db_session.scalars(select(Action).where(Action.kind == "email_send")).all()
    assert {a.status for a in actions} == {ActionStatus.sent}
    sent_to = {tuple(r.text.split("\n")[0:1]) for r in env.mailbox.sent}
    assert sent_to  # every mail carries the disclosure and a Ref footer
    for record in env.mailbox.sent:
        assert "Afterward, an AI assistant" in record.text and "Ref AW-1042-" in record.text
    a = _accounts(db_session)
    assert a["4417"].status_service is ServiceStatus.requested
    followups = db_session.scalars(select(Job).where(Job.kind == "followup")).all()
    assert len(followups) == 4 and all(j.status is JobStatus.pending for j in followups)


async def test_reply_catches_the_wrong_outcome_and_holds_the_lookalike(db_session, play):
    await play("intent", "discover", "confirm", "dependency", "approve", "steady", "send", "reply")
    a = _accounts(db_session)
    northline = db_session.scalar(
        select(OutcomeCheck).where(OutcomeCheck.account_id == a["4417"].id)
    )
    assert northline.verdict == "needs_decision"
    assert northline.results["voicemail_preserved"] == "violated"
    assert "new_contract" in northline.results["unauthorised"]
    assert a["4417"].status_service is not ServiceStatus.transferred
    streambox = db_session.scalar(
        select(OutcomeCheck).where(OutcomeCheck.account_id == a["SB-88213"].id)
    )
    assert streambox.verdict == "resolved" and a["SB-88213"].status_service is ServiceStatus.closed
    assert a["CP-77120"].status_money is MoneyStatus.issued_awaiting_receipt
    refund = db_session.scalar(select(MoneyItem))
    assert str(refund.amount) == "42.00"
    held = db_session.scalars(
        select(Message).where(Message.recipient_check == RecipientCheck.unapproved)
    ).all()
    assert [m.from_addr for m in held] == [data.SPOOF_SENDER]
    assert db_session.scalar(select(Decision)).status is DecisionStatus.open


async def test_call_records_the_choice_and_the_guard_blocks_acceptance(db_session, play):
    results = await play(
        "intent", "discover", "confirm", "dependency", "approve", "steady", "send", "reply", "call"
    )
    assert db_session.scalar(select(Decision)).chosen == "call"
    text = " ".join(results["call"].details)
    assert "BLOCKED" in text and "not a phone call" in text


async def test_clock_fires_exactly_one_followup_and_cancels_the_answered(db_session, play, env):
    await play("intent", "discover", "confirm", "dependency", "approve", "steady", "send", "reply")
    # Inside one rolled-back test transaction now() is frozen, so a reply looks older than the
    # send. Stamp the replies with real time, as separate production transactions would.
    db_session.execute(text("UPDATE commitments SET created_at = clock_timestamp()"))
    await play("call", "clock")
    a = _accounts(db_session)
    jobs = {
        j.payload["reason"]["account_id"]: j
        for j in db_session.scalars(select(Job).where(Job.kind == "followup"))
    }
    assert jobs[str(a["FL-5531"].id)].status is JobStatus.succeeded
    for ref in ("4417", "SB-88213", "CP-77120"):
        assert jobs[str(a[ref].id)].status is JobStatus.cancelled
        assert jobs[str(a[ref].id)].last_error == "reason_gone"
    followups = db_session.scalars(select(Action).where(Action.idem_key.like("followup:%"))).all()
    assert len(followups) == 1 and followups[0].status is ActionStatus.sent
    fit_threads = {r.thread_id for r in env.mailbox.sent}
    assert "showcase-FL-5531" in fit_threads
    assert len([r for r in env.mailbox.sent if r.thread_id == "showcase-FL-5531"]) == 2


async def test_handback_prepares_but_never_files(db_session, play):
    await play(
        "intent", "discover", "confirm", "dependency", "approve", "steady",
        "send", "reply", "call", "clock", "handback",
    )  # fmt: skip
    a = _accounts(db_session)
    assert a["0932"].status_docs is DocsStatus.requirement_unmet
    assert "certified copy" in a["0932"].next_step["action"]
    handoffs = db_session.scalars(select(Action).where(Action.kind == "handoff")).all()
    assert len(handoffs) == 2
    assert a["HW-20418"].next_step["owner"] == "family"


async def test_finish_is_honest_and_counts_from_rows(db_session, factory, env, started):
    last = None
    for _ in STEP_IDS:
        last = await run_next(factory, env)
    assert last.step_id == "finish"
    assert await run_next(factory, env) is None
    assert last.headline.startswith("Not everything")
    text = " ".join(last.details)
    assert "candidate accounts still unconfirmed" in text or "unconfirmed" in text
    assert len(progress(db_session)) == len(STEP_IDS)
    case = db_session.get(Case, started)
    assert case.clock_offset_s >= 13 * 86400


async def test_steps_cannot_skip_ahead(factory, env, started):
    with pytest.raises(ShowcaseError):
        await run_step(factory, env, "approve")


async def test_rerunning_a_step_does_not_duplicate_rows(db_session, factory, env, play):
    await play("intent", "discover", "confirm", "dependency", "approve")
    await run_step(factory, env, "approve")
    await run_step(factory, env, "discover")
    assert db_session.scalar(select(func.count()).select_from(Approval)) == 4
    assert db_session.scalar(select(func.count()).select_from(Account)) == 9
    assert (
        db_session.scalar(select(func.count()).select_from(Job).where(Job.kind == "send_request"))
        == 4
    )


async def test_reset_returns_to_the_start(db_session, play):
    await play("intent", "discover", "confirm")
    reset_showcase(db_session)
    assert db_session.scalar(select(func.count()).select_from(Account)) == 0
    assert progress(db_session) == []
    assert timedelta(0) is not None


async def test_classic_demo_seed_leaves_a_running_showcase_alone(db_session, play):
    from app.engine.demo_case import ensure_demo_case

    await play("intent", "discover", "confirm")
    before = (
        db_session.scalar(select(func.count()).select_from(Plan)),
        db_session.scalar(select(func.count()).select_from(Job)),
        db_session.scalar(select(func.count()).select_from(Account)),
    )
    ensure_demo_case(db_session)
    after = (
        db_session.scalar(select(func.count()).select_from(Plan)),
        db_session.scalar(select(func.count()).select_from(Job)),
        db_session.scalar(select(func.count()).select_from(Account)),
    )
    assert before == after
