"""Call room: changed terms void the old approval before any acceptance is spoken."""

import asyncio

from fastapi.testclient import TestClient

from app.call.acceptance import CallRoom, OfferedTerms, build_acceptance_sentence
from app.fakes import FakeCallSession
from app.web.factory import create_surface_app
from tests.web.conftest import token_for

ORIGINAL = OfferedTerms(12, "30", "kept", "kept")
CHANGED = OfferedTerms(12, "35", "kept", "kept")
CHANGE_LINE = "Sorry, that offer is now 12 months at $35 a month."


async def test_changed_terms_can_be_approved_without_speaking_the_old_sentence():
    session = FakeCallSession()
    room = CallRoom(session=session)
    await room.start()
    old_hash = await room.report_offered_terms(ORIGINAL)
    room.approve(old_hash)
    await room.queue_acceptance()
    new_hash = await room.report_offered_terms(CHANGED)
    assert room.approval_status == "void"
    assert session.played == []
    room.approve(new_hash)
    played = await room.try_play_acceptance()
    assert played is True
    assert build_acceptance_sentence(CHANGED) in session.played
    assert build_acceptance_sentence(ORIGINAL) not in session.played


def test_call_room_discards_acceptance_when_the_representative_changes_terms():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        token = token_for(surface.call_tokens, surface.demo_case_id)
        room = surface.calls[token]
        asyncio.run(_arm(room))
        sentence = build_acceptance_sentence(ORIGINAL)
        changed = client.post(f"/api/calls/{token}/turn", data={"text": CHANGE_LINE})
        assert changed.status_code == 200
        continued = client.post(f"/api/calls/{token}/continue", follow_redirects=False)
        assert continued.status_code == 303
        assert room.session.played == []
        assert room.approval_status == "void"
        assert sentence in room.session.discarded
        assert room.acceptance_played is False


async def _arm(room: CallRoom) -> None:
    await room.start()
    terms_hash = await room.report_offered_terms(ORIGINAL)
    room.approve(terms_hash)
    await room.queue_acceptance()
