"""The call socket carries server state only. Voice goes browser to OpenAI over WebRTC."""

from fastapi.testclient import TestClient

from app.call import router as call_router
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID
from tests.web.conftest import token_for


def _receive_until(ws, predicate, limit=40):
    seen = []
    for _ in range(limit):
        frame = ws.receive_json()
        seen.append(frame)
        if predicate(frame):
            return frame, seen
    raise AssertionError(f"frame not seen in {seen}")


def test_socket_refuses_a_call_that_was_not_started():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        token = token_for(surface.call_tokens, DEMO_CASE_ID)
        surface.calls[token].status = "none"
        with client.websocket_connect(f"/ws/calls/{token}") as ws:
            assert ws.receive_json() == {"kind": "not_started"}


def test_live_call_page_does_not_reload_itself(monkeypatch):
    monkeypatch.setattr(call_router, "realtime_allowed", lambda settings: True)
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
        client.post(f"/call/{token}/join")
        page = client.get(f"/call/{token}")
        assert "data-reload" not in page.text
        assert 'id="mic"' in page.text and "Start talking" in page.text
        assert "hold the button" not in page.text.lower()
