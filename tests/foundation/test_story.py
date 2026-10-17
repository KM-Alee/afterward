"""One story: Telegram turns and provider replies change the desk the judge is looking at."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai.schemas import ReplyOut
from app.conversation.demo_malik import run_malik_script
from app.fakes import FakeAI, FakeChannel, FakeMailbox
from app.runtime import after_turn
from app.story import NORTHLINE_FOOTER, fastn_reminder_succeeded, mark_request_sent, reflect_turn
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID, VARIANTS, build_surface
from tests.web.conftest import login, token_for

CONTRADICTORY = VARIANTS["nl_contradictory"]["text"]


def test_fastn_success_needs_a_run_id():
    assert fastn_reminder_succeeded(200, {}) is False
    assert fastn_reminder_succeeded(200, "ok") is False
    assert fastn_reminder_succeeded(404, {"id": "run-1"}) is False
    assert fastn_reminder_succeeded(200, {"executionId": "run-1"}) is True


def _commitment(action, status, facts, interpretation="clear", hint="Line", quote=""):
    return {
        "account_hint": hint,
        "action": action,
        "status": status,
        "negated": False,
        "conditions_or_requirements": [],
        "facts": [{"key": k, "value": v, "evidence_quote": q} for k, v, q in facts],
        "scope": "this_service",
        "effective_date": None,
        "evidence_quote": quote,
        "interpretation": interpretation,
    }


def _live_reading(interpretation: str = "clear") -> ReplyOut:
    """What the live model returned for the contradictory reply, hint and all."""
    return ReplyOut.model_validate(
        {
            "commitments": [
                _commitment(
                    "transfer",
                    "completed",
                    [
                        ("new_holder", "Mrs Malik", "Line transferred to Mrs Malik"),
                        ("contract_months", "24", "new 24-month plan"),
                    ],
                    interpretation,
                    quote="Line transferred to Mrs Malik on a new 24-month plan.",
                ),
                _commitment(
                    "service_change",
                    "promised",
                    [("voicemail_preserved", "false", "Voicemail will be reset during migration")],
                    interpretation,
                    quote="Voicemail will be reset during migration.",
                ),
            ],
            "asks_for_documents": [],
            "is_marketing_to_deceased": False,
        }
    )


class _Reader:
    def __init__(self, reply: ReplyOut) -> None:
        self.reply = reply

    async def structured(self, role, schema, messages, images=None):
        del role, schema, messages, images
        return self.reply


def _send_northline(client: TestClient, reading: ReplyOut) -> str:
    client.app.state.reply_reader = _Reader(reading)
    surface = client.app.state.surface
    provider = token_for(surface.provider_tokens, DEMO_CASE_ID)
    sent = client.post(
        "/api/provider/send",
        data={"token": provider, "provider": "northline", "variant": "nl_contradictory"},
        follow_redirects=False,
    )
    assert sent.status_code == 303
    login(client)
    return client.get(f"/desk/{DEMO_CASE_ID}").text


def test_contradictory_reply_shows_the_broken_conditions_on_the_desk():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        desk = _send_northline(client, _live_reading())
        outcome = client.app.state.surface.cases[DEMO_CASE_ID].outcome
        states = {check.label: check.chip_text for check in outcome.checks}
        assert states == {
            "Voicemail kept": "Broken",
            "Number kept": "Not stated",
            "No new contract": "Broken",
        }
        assert outcome.verdict_kind == "notdone"
        assert outcome.verdict_text.startswith("Not done.")
        assert "voicemail kept, no new contract" in outcome.verdict_text
        assert "Not done. Broken: voicemail kept, no new contract." in desk
        assert outcome.quote == CONTRADICTORY


def test_ambiguous_reading_is_not_turned_into_broken_conditions():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        _send_northline(client, _live_reading("ambiguous"))
        outcome = client.app.state.surface.cases[DEMO_CASE_ID].outcome
        assert {check.chip_text for check in outcome.checks} == {"Not stated"}
        assert outcome.verdict_kind == "open"
        assert "not clear enough" in outcome.verdict_text
        tile = next(
            t for t in client.app.state.surface.cases[DEMO_CASE_ID].accounts if t.id == "nl4417"
        )
        assert tile.bucket_text == "Unclear reply"
        assert all(check.chip_text != "Broken" for check in tile.conditions)


async def _malik():
    result = await run_malik_script(FakeAI(), FakeChannel())
    return result.conversation


@pytest.mark.asyncio
async def test_amina_is_asked_after_joining_and_her_answer_changes_the_desk_plan():
    conversation = await _malik()
    surface = build_surface("")
    app = SimpleNamespace(state=SimpleNamespace(surface=surface, settings=None))
    joined = [SimpleNamespace(kind="invite_joined", to="2002", text="joined")]
    replies = await after_turn(app, conversation, "2002", joined)
    assert [reply.kind for reply in replies] == ["invite_joined", "dependency_question"]
    board = surface.cases[DEMO_CASE_ID]
    version = board.outcome.plan_version
    reflect_turn(surface, conversation, ["dependency_ack", "plan_revision", "approval_card"])
    reflect_turn(surface, conversation, ["plan_revision"])
    assert board.outcome.plan_version == version + 1
    assert "Keep the voicemail" in board.outcome.requested_conditions
    assert board.outcome.verdict_text == "Waiting for Sara to approve this plan."
    assert any("Amina's answer changed the plan" in event.text for event in board.events)


@pytest.mark.asyncio
async def test_approval_without_a_mailbox_sends_nothing_and_says_so():
    conversation = await _malik()
    conversation.state.approval_choice = None
    surface = build_surface("")
    app = SimpleNamespace(state=SimpleNamespace(surface=surface, settings=None))
    replies = await conversation.handle_button("1001", "approve_plan")
    replies = await after_turn(app, conversation, "1001", replies)
    assert replies[-1].kind == "request_sent"
    assert "nothing was sent" in replies[-1].text
    board = surface.cases[DEMO_CASE_ID]
    assert any("nothing was sent" in event.text for event in board.events)


def _mail_settings():
    secret = SimpleNamespace(get_secret_value=lambda: "set")
    return SimpleNamespace(
        family_mailbox="family@demo.example",
        providers_mailbox="providers@demo.example",
        google_client_id=secret,
        google_refresh_token_family=secret,
    )


@pytest.mark.asyncio
async def test_approval_sends_the_card_once_to_the_demo_provider_inbox(monkeypatch):
    conversation = await _malik()
    mailbox = FakeMailbox()
    inserted: list[dict] = []

    class _Calendar:
        def insert_event(self, body):
            inserted.append(body)
            return "evt"

    monkeypatch.setattr("app.integrations.google.gmail_mailbox_for", lambda s, role: mailbox)
    monkeypatch.setattr("app.integrations.google.calendar_transport_for", lambda s: _Calendar())
    surface = build_surface("")
    text = await mark_request_sent(surface, _mail_settings(), conversation.state.approval)
    assert "Gmail" in text
    assert len(mailbox.sent) == 1
    record = mailbox.sent[0]
    assert record.footer_ref == NORTHLINE_FOOTER
    assert "keep the voicemail" in record.text
    assert len(inserted) == 1
    tile = next(t for t in surface.cases[DEMO_CASE_ID].accounts if t.id == "nl4417")
    assert tile.bucket_text == "Waiting"


@pytest.mark.asyncio
async def test_a_card_for_another_recipient_is_not_sent(monkeypatch):
    conversation = await _malik()
    mailbox = FakeMailbox()
    monkeypatch.setattr("app.integrations.google.gmail_mailbox_for", lambda s, role: mailbox)
    card = conversation.state.approval
    forged = SimpleNamespace(**{**card.__dict__, "recipient": "attacker@example.com"})
    surface = build_surface("")
    text = await mark_request_sent(surface, _mail_settings(), forged)
    assert mailbox.sent == []
    assert "nothing was sent" in text


def test_plus_fourteen_sends_one_follow_up_and_finds_it_before_saying_so():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        login(client)
        surface = client.app.state.surface
        board = surface.cases[DEMO_CASE_ID]
        assert board.delivery == "uncertain"
        client.post(f"/api/cases/{DEMO_CASE_ID}/clock", data={"advance_days": "14"})
        client.post(f"/api/cases/{DEMO_CASE_ID}/clock", data={"advance_days": "14"})
        follow_ups = [r for r in surface.mailbox.sent if "AW-1042-FL1" in r.text]
        assert len(follow_ups) == 1
        assert board.delivery == "reconciled"


def test_reset_restores_the_story_and_needs_the_desk_passcode():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        denied = client.post(f"/api/cases/{DEMO_CASE_ID}/reset", follow_redirects=False)
        assert denied.status_code == 401
        _send_northline(client, _live_reading())
        call = token_for(surface.call_tokens, DEMO_CASE_ID)
        client.post(f"/api/calls/{call}/turn", data={"text": "12 months at $30 a month."})
        reset = client.post(f"/api/cases/{DEMO_CASE_ID}/reset", follow_redirects=False)
        assert reset.status_code == 303
        assert surface.calls[call].terms is None
        assert surface.mailbox.sent == []
        assert surface.cases[DEMO_CASE_ID].outcome.quote == CONTRADICTORY
        assert len(surface.cases[DEMO_CASE_ID].events) == 5
