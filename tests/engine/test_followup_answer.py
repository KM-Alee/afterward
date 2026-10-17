"""A gentle follow-up asks the family once; only their button sends or cancels it."""

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.engine import executors  # noqa: F401  (registers the engine kinds)
from app.engine.clock import advance_case_clock
from app.engine.demo_case import ensure_demo_case
from app.engine.errors import EngineError
from app.engine.followups import answer_followup
from app.engine.runner import RunContext, run_due_jobs
from app.models import Decision, DecisionStatus, Job, JobStatus

pytestmark = pytest.mark.db


@pytest.fixture
def factory(db_session):
    @contextmanager
    def make():
        yield db_session

    return make


async def _fire(db_session, factory):
    asked: list[tuple[str, list]] = []

    async def ask(text, buttons):
        asked.append((text, buttons))
        return True

    case_id = ensure_demo_case(db_session)
    advance_case_clock(db_session, case_id, 15 * 24 * 3600)
    db_session.commit()
    ctx = RunContext(settings=None, ask=ask)
    await run_due_jobs(factory, ctx, wall=datetime.now(UTC))
    decision = db_session.scalar(
        select(Decision).where(Decision.case_id == case_id, Decision.kind == "followup")
    )
    return case_id, decision, asked, ctx


async def test_family_is_asked_once_with_two_buttons(db_session, factory):
    case_id, decision, asked, ctx = await _fire(db_session, factory)
    assert decision is not None and decision.status is DecisionStatus.open
    assert len(asked) == 1
    ids = [key for key, _ in asked[0][1]]
    assert ids == [f"fu:{decision.id}:send", f"fu:{decision.id}:not_now"]
    advance_case_clock(db_session, case_id, 2 * 24 * 3600)
    db_session.commit()
    await run_due_jobs(factory, ctx, wall=datetime.now(UTC))
    assert len(asked) == 1  # parked again, not asked again


async def test_send_queues_send_request_under_the_same_approval(db_session, factory):
    case_id, decision, _, _ = await _fire(db_session, factory)
    followup = db_session.get(Job, decision.payload["job_id"])
    text = await answer_followup(db_session, decision.id, "send", actor="Sara")
    assert "queued" in text
    assert followup.status is JobStatus.succeeded
    send = db_session.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "send_request"))
    assert send is not None and send.payload["approval_id"] == followup.payload["approval_id"]
    with pytest.raises(EngineError):
        await answer_followup(db_session, decision.id, "send", actor="Sara")


async def test_not_now_cancels_and_sends_nothing(db_session, factory):
    case_id, decision, _, _ = await _fire(db_session, factory)
    await answer_followup(db_session, decision.id, "not_now", actor="Sara")
    followup = db_session.get(Job, decision.payload["job_id"])
    assert followup.status is JobStatus.cancelled
    sends = db_session.scalars(
        select(Job).where(Job.case_id == case_id, Job.kind == "send_request")
    )
    assert list(sends) == []


async def test_unknown_choice_is_refused(db_session, factory):
    _, decision, _, _ = await _fire(db_session, factory)
    with pytest.raises(EngineError):
        await answer_followup(db_session, decision.id, "accept_anything", actor="Sara")
    assert decision.status is DecisionStatus.open
