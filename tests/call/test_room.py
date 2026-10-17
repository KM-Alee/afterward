"""Call room: the model cannot accept, and obsolete audio never plays."""

import pytest
from fastapi.testclient import TestClient

from app.call.acceptance import CallRoom, OfferedTerms, build_acceptance_sentence
from app.call.tools import build_call_agent, call_tools
from app.contracts import CALL_TOOL_NAMES, CallEventKind, ContractError, make_call_agent
from app.fakes import FakeCallSession
from app.web.factory import create_surface_app
from app.web.state import EMPTY_CASE_ID
from tests.web.conftest import token_for


def test_model_cannot_accept():
    tools = call_tools()
    names = [str(getattr(tool, "name", "")) for tool in tools]
    assert names == list(CALL_TOOL_NAMES)
    assert all("accept" not in name.lower() for name in names)
    decision = next(tool for tool in tools if tool.name == "request_family_decision")
    assert decision.needs_approval is True
    agent = build_call_agent()
    assert [tool.name for tool in agent.tools] == list(CALL_TOOL_NAMES)

    class AcceptTool:
        name = "accept_terms"

    with pytest.raises(ContractError):
        make_call_agent(name="call_agent", instructions="no", tools=[AcceptTool()])


async def test_model_speech_does_not_play_acceptance():
    session = FakeCallSession()
    room = CallRoom(session=session)
    await room.start()
    tripped = await room.screen_model_speech("We accept those terms. Go ahead.")
    assert tripped is True
    assert session.played == []
    assert room.acceptance_played is False
    assert session.events()[0].kind is CallEventKind.guardrail_tripped
    assert not hasattr(room, "accept")


async def test_terms_change_voids_approval_before_acceptance_audio():
    session = FakeCallSession()
    room = CallRoom(session=session)
    await room.start()
    original = OfferedTerms(12, "30", "kept", "kept")
    terms_hash = await room.report_offered_terms(original)
    room.approve(terms_hash)
    sentence = build_acceptance_sentence(original)
    await room.queue_acceptance()
    assert session.played == []
    assert sentence in session._queued
    await room.on_representative_speech()
    await room.report_offered_terms(OfferedTerms(12, "35", "kept", "kept"))
    played = await room.try_play_acceptance()
    assert played is False
    assert session.played == []
    assert room.approval_status == "void"
    assert sentence in session.discarded
    assert room.acceptance_played is False


async def test_obsolete_queued_audio_is_discarded():
    session = FakeCallSession()
    room = CallRoom(session=session)
    await room.start()
    terms_hash = await room.report_offered_terms(OfferedTerms(12, "30", "kept", "kept"))
    room.approve(terms_hash)
    await room.queue_acceptance()
    assert session.played == []
    await room.discard_obsolete()
    await session.resume_acceptance()
    assert session.played == []
    assert session.discarded
    assert room.acceptance_played is False


def test_typed_turn_end_to_end_on_fakes():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        token = token_for(surface.call_tokens, surface.demo_case_id)
        page = client.get(f"/call/{token}")
        assert page.status_code == 200
        assert "Browser call, not a phone call" in page.text
        assert "not a guarantee" in page.text
        assert "Join the call" in page.text  # controls appear once the call is live
        sent = client.post(
            f"/api/calls/{token}/turn",
            data={"text": "We can keep the number."},
        )
        assert sent.status_code == 200
        assert "We can keep the number." in sent.text
        assert "You, typed" in sent.text
        assert "Send this line" in sent.text
        assert "Type what you would say" in sent.text
        room = surface.calls[token]
        assert room.session.typed_turns == ["We can keep the number."]
        assert room.session.suspended is True
        assert room.session.played == []
        assert room.latency[0]["via"] == "typed"
        empty = token_for(surface.call_tokens, EMPTY_CASE_ID)
        quiet = client.get(f"/call/{empty}")
        assert quiet.status_code == 200
        assert "No call yet" in quiet.text
        assert client.get("/call/not-a-real-token").status_code == 404
        refused = client.post(f"/api/calls/{token}/dial")
        assert refused.status_code == 403
        assert "not a phone call" in refused.text


def test_speech_check_keeps_call_manners_and_stops_agreement():
    from app.call.guard import commitment_tripped

    for fine in (
        "Please go ahead, I'm listening.",
        "Nothing has been agreed yet; the family decides.",
        "Go ahead whenever you're ready.",
        "I can't accept terms myself.",
    ):
        assert not commitment_tripped(fine), fine
    for stop in (
        "We accept the 24-month plan.",
        "Agreed, go ahead.",
        "Yes, go ahead with the transfer.",
        "It's a deal.",
        "Okay, go ahead and set it up.",
        "We'll take it.",
    ):
        assert commitment_tripped(stop), stop
