"""Call room in the browser: the family approves exact terms; the model only speaks."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.call.acceptance import OfferedTerms, build_acceptance_sentence, offered_terms_from_text
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID
from tests.web.conftest import token_for

OFFER = "We can keep the number and voicemail for 12 months at $30 a month."
CHANGE = "Sorry, that offer is now 12 months at $35 a month."


def _tokens(client: TestClient) -> tuple[str, str]:
    surface = client.app.state.surface
    return (
        token_for(surface.call_tokens, DEMO_CASE_ID),
        token_for(surface.family_tokens, DEMO_CASE_ID),
    )


def test_first_offer_is_read_from_the_representative_words():
    terms = offered_terms_from_text(OFFER, None)
    assert terms == OfferedTerms(12, "30", "kept", "kept")
    lost = offered_terms_from_text("12 months at $30, the voicemail will be reset.", None)
    assert lost is not None and lost.voicemail_preserved == "not kept"
    assert "voicemail" not in build_acceptance_sentence(lost)


def test_offer_asks_sara_and_only_her_approval_speaks_the_fixed_sentence():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        call, family = _tokens(client)
        room = client.app.state.surface.calls[call]
        client.post(f"/call/{call}/join")
        client.post(f"/api/calls/{call}/turn", data={"text": OFFER})
        assert room.terms == OfferedTerms(12, "30", "kept", "kept")
        assert room.approval_status == "pending"
        assert any(turn.kind == "decision" for turn in room.turns)
        agent = [turn for turn in room.turns if turn.who == "agent" and turn.kind == "model"]
        assert agent and agent[-1].via == "scripted"
        assert room.session.played == []
        page = client.get(f"/family/{family}").text
        assert "Northline offered 12 months at $30 a month" in page
        stale = client.post(
            f"/family/{family}/call", data={"choice": "approve", "terms_hash": "old"}
        )
        assert stale.status_code == 409
        assert room.approval_status == "pending"
        client.post(
            f"/family/{family}/call", data={"choice": "approve", "terms_hash": room.terms_hash}
        )
        assert room.approval_status == "approved"
        assert room.session.played == []
        client.post(f"/api/calls/{call}/continue")
        sentence = build_acceptance_sentence(room.terms)
        assert room.session.played == [sentence]


def test_price_change_after_approval_voids_the_sentence_and_asks_again():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        call, family = _tokens(client)
        room = client.app.state.surface.calls[call]
        client.post(f"/api/calls/{call}/turn", data={"text": OFFER})
        client.post(
            f"/family/{family}/call", data={"choice": "approve", "terms_hash": room.terms_hash}
        )
        old = build_acceptance_sentence(room.terms)
        client.post(f"/api/calls/{call}/turn", data={"text": CHANGE})
        assert room.approval_status == "void"
        client.post(f"/api/calls/{call}/continue")
        assert room.session.played == []
        assert old in room.session.discarded
        asked = [turn for turn in room.turns if turn.kind == "decision" and "$35" in turn.text]
        assert len(asked) == 1
        page = client.get(f"/family/{family}").text
        assert "earlier approval no longer counts" in page


def test_model_agreement_is_stopped_by_the_speech_check(monkeypatch):
    async def agreeing(settings, room, text):
        return "Great, we accept those terms. Go ahead."

    monkeypatch.setattr("app.call.live.realtime_reply", agreeing)
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        call, _family = _tokens(client)
        room = client.app.state.surface.calls[call]
        client.post(f"/api/calls/{call}/turn", data={"text": OFFER})
        assert room.guard_trips == ["commitment"]
        assert not any("we accept" in turn.text.lower() for turn in room.turns)
        assert room.approval_status == "pending"
        assert room.session.played == []


def test_realtime_reply_is_labelled(monkeypatch):
    async def polite(settings, room, text):
        return "Thank you. The family decides; I'll ask them."

    monkeypatch.setattr("app.call.live.realtime_reply", polite)
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        call, _family = _tokens(client)
        page = client.post(f"/api/calls/{call}/turn", data={"text": "Hello."}).text
        assert "live realtime model, text" in page


def test_voice_history_keeps_the_assistant_line_only():
    from app.call.live import _last_assistant

    history = [
        SimpleNamespace(role="user", content=[SimpleNamespace(text="12 months at $30")]),
        SimpleNamespace(
            role="assistant", content=[SimpleNamespace(transcript="I'll ask the family.")]
        ),
    ]
    assert _last_assistant(history) == "I'll ask the family."
    assert _last_assistant("nope") == ""
