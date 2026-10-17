"""The autoplay narration route: auth, input check, voice failure fallback, caching."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.ai.client import SpeechChunk
from app.web.factory import create_surface_app
from tests.web.conftest import PASSCODE, login

pytestmark = pytest.mark.db


class _Voice:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def speak_stream(self, text, *, voice=None, audio_format="pcm"):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        yield SpeechChunk(audio=b"OggS-" + text.encode(), audio_format=audio_format)


@pytest.fixture
def client(db_session):
    app = create_surface_app(demo_passcode=PASSCODE)

    @contextmanager
    def factory():
        yield db_session

    app.state.session_factory = factory
    with TestClient(app) as test_client:
        yield test_client


def test_denied_without_login(client):
    res = client.post("/api/showcase/narrate", json={"text": "hello"}, follow_redirects=False)
    assert res.status_code in (303, 401, 403)


def test_empty_text_is_422(client):
    login(client)
    client.app.state.showcase_ai = _Voice()
    for body in ({"text": ""}, {"text": "   "}, {}):
        assert client.post("/api/showcase/narrate", json=body).status_code == 422


def test_no_voice_configured_falls_back(client):
    login(client)
    res = client.post("/api/showcase/narrate", json={"text": "hello"})
    assert res.status_code == 503
    assert res.json()["fallback"] == "browser"


def test_voice_failure_is_a_clear_fallback(client):
    login(client)
    client.app.state.showcase_ai = _Voice(fail=True)
    res = client.post("/api/showcase/narrate", json={"text": "hello"})
    assert res.status_code == 502
    body = res.json()
    assert body["fallback"] == "browser" and "boom" not in res.text


def test_audio_is_returned_and_cached(client):
    login(client)
    voice = _Voice()
    client.app.state.showcase_ai = voice
    first = client.post("/api/showcase/narrate", json={"text": "hello"})
    second = client.post("/api/showcase/narrate", json={"text": "hello"})
    assert first.status_code == 200 and first.headers["content-type"] == "audio/ogg"
    assert first.content == second.content == b"OggS-hello"
    assert voice.calls == 1
    client.post("/api/showcase/narrate", json={"text": "other"})
    assert voice.calls == 2


def test_tour_carries_autoplay_lines(client):
    login(client)
    stops = client.get("/api/showcase/tour", headers={"accept": "application/json"}).json()["stops"]
    assert len(stops) == 12 and all(s["autoplay"]["say"] and s["autoplay"]["dwell"] for s in stops)
