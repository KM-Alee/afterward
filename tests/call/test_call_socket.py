"""The live call runs over one websocket: lines in, transcript and state out, no reloads."""

import time

from fastapi.testclient import TestClient

from app.call import router as call_router
from app.call.realtime_session import OpenAIRealtimeSession
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID
from tests.call.test_realtime_session import FakeRealtime, _msg
from tests.web.conftest import token_for


def _receive_until(ws, predicate, limit=40):
    seen = []
    for _ in range(limit):
        frame = ws.receive_json()
        seen.append(frame)
        if predicate(frame):
            return frame, seen
    raise AssertionError(f"frame not seen in {seen}")


def _live_app(monkeypatch):
    fakes: list[FakeRealtime] = []

    class Session(OpenAIRealtimeSession):
        def __init__(self, settings=None, *, room=None, **_):
            async def factory():
                fake = FakeRealtime()
                fakes.append(fake)
                return fake

            super().__init__(settings, room=room, realtime_factory=factory)

    monkeypatch.setattr(call_router, "realtime_allowed", lambda settings: True)
    monkeypatch.setattr(call_router, "OpenAIRealtimeSession", Session)
    return create_surface_app(demo_passcode="fixture-passcode"), fakes


def test_line_over_socket_streams_turns_without_a_duplicate(monkeypatch):
    app, fakes = _live_app(monkeypatch)
    with TestClient(app) as client:
        token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
        with client.websocket_connect(f"/ws/calls/{token}") as ws:
            ready, _ = _receive_until(ws, lambda f: f["kind"] == "call.ready")
            assert ready["mode"] == "realtime" and ready["phone"] is False
            ws.send_json({"type": "line", "text": "We can keep it for 12 months at $30 a month."})
            rep, _ = _receive_until(ws, lambda f: f["kind"] == "turn" and f["who"] == "rep")
            assert rep["via"] == "typed"
            state, _ = _receive_until(ws, lambda f: f["kind"] == "state" and f["terms"])
            assert state["terms"] == {"months": 12, "price": "30"}
            assert state["approval"] == "pending"
            fake = fakes[-1]
            assert fake.messages == ["We can keep it for 12 months at $30 a month."]
            # The model echoes the typed line back as a user item, then answers.
            history = [
                _msg("user", "We can keep it for 12 months at $30 a month.", "u1"),
                _msg("assistant", "Thank you. I have noted that offer.", "a1"),
            ]
            fake.feed(type="history_updated", history=history)
            agent, seen = _receive_until(ws, lambda f: f["kind"] == "turn" and f["who"] == "agent")
            assert agent["via"] == "realtime"
            assert not [f for f in seen if f["kind"] == "turn" and f["who"] == "rep"]
        room = client.app.state.surface.calls[token]
        reps = [t for t in room.turns if t.who == "rep"]
        assert len(reps) == 1


def test_mic_audio_reaches_the_model_and_reply_audio_comes_back(monkeypatch):
    app, fakes = _live_app(monkeypatch)
    with TestClient(app) as client:
        token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
        with client.websocket_connect(f"/ws/calls/{token}") as ws:
            _receive_until(ws, lambda f: f["kind"] == "call.ready")
            ws.send_bytes(b"\x01\x00" * 480)
            fake = fakes[-1]
            for _ in range(50):
                if fake.audio:
                    break
                time.sleep(0.01)
            assert fake.audio and fake.audio[0] == b"\x01\x00" * 480
            fake.feed(type="audio", audio=type("A", (), {"data": b"\x02\x00" * 240})())
            for _ in range(40):
                frame = ws.receive()
                if frame.get("bytes"):
                    assert frame["bytes"] == b"\x02\x00" * 240
                    break
            else:
                raise AssertionError("no reply audio")


def test_socket_refuses_a_call_that_was_not_started():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        token = token_for(surface.call_tokens, DEMO_CASE_ID)
        surface.calls[token].status = "none"
        with client.websocket_connect(f"/ws/calls/{token}") as ws:
            assert ws.receive_json() == {"kind": "not_started"}


def test_live_call_page_does_not_reload_itself(monkeypatch):
    app, _ = _live_app(monkeypatch)
    with TestClient(app) as client:
        token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
        client.post(f"/call/{token}/join")
        page = client.get(f"/call/{token}")
        assert "data-reload" not in page.text
        assert 'id="mic"' in page.text and "Start talking" in page.text
        assert "hold the button" not in page.text.lower()
