"""Outbound executors: send, follow-up, hand-off, reconcile and calendar."""

import pytest
from sqlalchemy import select

from app.contracts import SqlEventBus
from app.fakes.mailbox import FakeMailbox
from app.mail.errors import DeliveryUncertain, MailError
from app.mail.outbound import (
    execute_action,
    execute_followup,
    execute_send_request,
    reconcile_action,
    visible_ref,
)
from app.models import Action, ActionStatus, CaseControl, Event, Monitoring
from tests.mail.support import FAMILY, account_by_ref, email_action, malik


def test_visible_ref_uses_the_case_ref_once():
    assert visible_ref("AW-1042", "1") == "AW-1042-1"
    assert visible_ref("1042", "1") == "AW-1042-1"


class _UncertainThenOk(FakeMailbox):
    def __init__(self) -> None:
        super().__init__()
        self.fail_once = True

    async def send(self, request):
        if self.fail_once:
            self.fail_once = False
            raise DeliveryUncertain("Gmail send timed out")
        return await super().send(request)


class _Calendar:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.bodies: list[dict] = []

    def insert_event(self, body: dict) -> str:
        if self.fail:
            raise MailError("Calendar insert failed")
        self.bodies.append(body)
        return "evt-1"


@pytest.mark.db
@pytest.mark.asyncio
async def test_followup_handoff_hold_and_reconcile(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    crescent = account_by_ref(db_session, case.id, "0932")
    family = FakeMailbox()
    bus = SqlEventBus()
    first = email_action(db_session, case, account, idem_key="send:4417:a", action_key="1")
    await execute_send_request(db_session, first, mailbox=family, bus=bus)
    follow = email_action(
        db_session,
        case,
        account,
        idem_key="follow:4417:2",
        action_key="2",
        body="",
        thread_id=first.request["thread_id"],
        in_reply_to=first.request["rfc_message_id"],
    )
    await execute_followup(db_session, follow, mailbox=family, bus=bus)
    assert follow.status == ActionStatus.sent
    assert "following up" in family.sent[1].text
    assert "Ref AW-1042-2" in family.sent[1].text
    assert family.sent[1].thread_id == first.request["thread_id"]

    branch = email_action(db_session, case, crescent, idem_key="send:0932:1", action_key="9")
    handoff = await execute_send_request(db_session, branch, mailbox=family, bus=bus)
    assert handoff.kind == "handoff"
    assert handoff.status == ActionStatus.sent
    assert branch.status == ActionStatus.failed
    assert branch.request["blocked"] == "channel_not_email"
    assert len(family.sent) == 2

    direct = Action(
        case_id=case.id,
        kind="handoff",
        idem_key="handoff:phone:1",
        status=ActionStatus.pending,
        request={"channel": "phone", "provider": "Crescent Bank", "account_id": str(crescent.id)},
    )
    db_session.add(direct)
    db_session.flush()
    await execute_action(db_session, direct, mailbox=family, bus=bus)
    assert direct.status == ActionStatus.sent
    assert len(family.sent) == 2

    case.control = CaseControl.hold
    held = email_action(db_session, case, account, idem_key="send:4417:held", action_key="5")
    await execute_send_request(db_session, held, mailbox=family, bus=bus)
    assert held.status == ActionStatus.pending
    assert held.request["blocked"] == "hold"
    assert len(family.sent) == 2
    case.control = CaseControl.active

    case.monitoring = Monitoring.interrupted
    paused = email_action(db_session, case, account, idem_key="send:4417:paused", action_key="6")
    await execute_send_request(db_session, paused, mailbox=family, bus=bus)
    assert paused.status == ActionStatus.pending
    assert paused.request["blocked"] == "monitoring_interrupted"
    case.monitoring = Monitoring.ok


@pytest.mark.db
@pytest.mark.asyncio
async def test_uncertain_send_reconciles_or_retries_once(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    flaky = _UncertainThenOk()
    action = email_action(db_session, case, account, idem_key="send:4417:unsure", action_key="7")
    await execute_send_request(db_session, action, mailbox=flaky, bus=None)
    assert action.status == ActionStatus.uncertain
    assert action.attempts == 1
    assert "body" in action.request
    assert flaky.sent == []

    recovered = await reconcile_action(db_session, action, flaky)
    assert recovered.status == ActionStatus.sent
    assert len(flaky.sent) == 1
    assert "Ref AW-1042-7" in flaky.sent[0].text

    found = await reconcile_action(db_session, action, flaky)
    assert found.status == ActionStatus.reconciled
    assert found.external_id == flaky.sent[0].gmail_id

    stuck = email_action(
        db_session,
        case,
        account,
        idem_key="send:4417:stuck",
        action_key="8",
        status=ActionStatus.uncertain,
        attempts=2,
    )
    stuck.request = {**stuck.request, "footer_ref": "AW-1042-8", "mailbox": FAMILY}
    quiet = FakeMailbox()
    await reconcile_action(db_session, stuck, quiet)
    assert stuck.status == ActionStatus.uncertain
    assert quiet.sent == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_calendar_insert_uses_an_action_and_reminder_overrides(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "CP-77120")
    calendar = _Calendar()
    bus = SqlEventBus()
    action = Action(
        case_id=case.id,
        kind="calendar_insert",
        idem_key="cal:city:1",
        status=ActionStatus.pending,
        request={
            "account_id": str(account.id),
            "summary": "Check the City Power bill",
            "start": "2026-04-30T09:00:00+00:00",
            "end": "2026-04-30T09:30:00+00:00",
            "reminders": [{"method": "popup", "minutes": 60}],
        },
    )
    db_session.add(action)
    db_session.flush()
    await execute_action(db_session, action, calendar=calendar, bus=bus)
    assert action.status == ActionStatus.sent
    assert action.external_id == "evt-1"
    assert calendar.bodies[0]["reminders"]["useDefault"] is False
    assert calendar.bodies[0]["reminders"]["overrides"] == [{"method": "popup", "minutes": 60}]
    event = db_session.scalar(select(Event).where(Event.kind == "calendar_inserted"))
    assert event is not None
    assert event.payload["event_id"] == "evt-1"

    failed = Action(
        case_id=case.id,
        kind="calendar_insert",
        idem_key="cal:city:fail",
        status=ActionStatus.pending,
        request={
            "summary": "Check",
            "start": "2026-04-30T09:00:00+00:00",
            "end": "2026-04-30T09:30:00+00:00",
        },
    )
    db_session.add(failed)
    db_session.flush()
    await execute_action(db_session, failed, calendar=_Calendar(fail=True), bus=bus)
    assert failed.status == ActionStatus.failed
