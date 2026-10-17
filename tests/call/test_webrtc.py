"""Browser-direct voice: session minting, server tools, transcript record, speech check."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.call import router as call_router
from app.call import webrtc
from app.call.acceptance import OfferedTerms, build_acceptance_sentence
from app.config import Settings
from app.contracts import CALL_TOOL_NAMES
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID
from tests.web.conftest import token_for

KEY = "fixture-value-only"
EPHEMERAL = "fixture-ephemeral-value"
OFFER = "We can keep the number and voicemail for 12 months at $30 a month."
CHANGE = "Sorry, that is now 12 months at $35 a month."


@pytest.fixture
def seen_requests():
    return []


@pytest.fixture
def minted(monkeypatch, seen_requests):
    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"value": EPHEMERAL, "expires_at": 1999999999})

    monkeypatch.setattr(webrtc, "_TRANSPORT", httpx.MockTransport(handler))


def _client(key=KEY):
    app = create_surface_app(demo_passcode="fixture-passcode")
    app.state.settings = Settings(openai_api_key=SecretStr(key))
    return TestClient(app)


def _open(client: TestClient):
    token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
    client.post(f"/call/{token}/join")
    return token, client.app.state.surface.calls[token]


def _say(client, token, who, text, item_id):
    body = {"who": who, "text": text, "item_id": item_id}
    return client.post(f"/api/calls/{token}/transcript", json=body)


def test_session_returns_only_the_ephemeral_secret(minted, seen_requests, caplog):
    with _client() as client:
        token, _ = _open(client)
        res = client.post(f"/api/calls/{token}/session")
        assert res.status_code == 200
        body = res.json()
        assert body["client_secret"] == EPHEMERAL
        assert body["model"] == "gpt-realtime-2.1"
        assert KEY not in res.text and KEY not in caplog.text
        sent = seen_requests[0]
        assert sent.headers["authorization"] == f"Bearer {KEY}"
        payload = json.loads(sent.content)["session"]
        assert payload["type"] == "realtime"
        assert payload["audio"]["input"]["transcription"]["model"]
        vad = payload["audio"]["input"]["turn_detection"]
        assert vad["type"] == "server_vad" and vad["interrupt_response"] is True
        assert vad["create_response"] is True and vad["silence_duration_ms"] == 550
        names = [t["name"] for t in payload["tools"]]
        assert tuple(names) == CALL_TOOL_NAMES
        assert not any("accept" in n for n in names)
        assert "cannot accept" in payload["instructions"]


def test_session_errors_show_the_provider_message_not_the_key(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    monkeypatch.setattr(webrtc, "_TRANSPORT", httpx.MockTransport(handler))
    with _client() as client:
        token, _ = _open(client)
        res = client.post(f"/api/calls/{token}/session")
        assert res.status_code == 502
        assert "Incorrect API key" in res.json()["error"] and KEY not in res.text


def test_bad_transcription_model_falls_back_once(monkeypatch):
    models = []

    def handler(request):
        session = json.loads(request.content)["session"]
        models.append(session["audio"]["input"]["transcription"]["model"])
        if len(models) == 1:
            return httpx.Response(400, json={"error": {"message": "Invalid transcription model"}})
        return httpx.Response(200, json={"value": EPHEMERAL, "expires_at": 1})

    monkeypatch.setattr(webrtc, "_TRANSPORT", httpx.MockTransport(handler))
    settings = Settings(openai_api_key=SecretStr(KEY), realtime_transcribe_model="gpt-bogus")
    app = create_surface_app(demo_passcode="fixture-passcode")
    app.state.settings = settings
    with TestClient(app) as client:
        token, _ = _open(client)
        assert client.post(f"/api/calls/{token}/session").status_code == 200
        assert models == ["gpt-bogus", "gpt-4o-mini-transcribe"]


def test_session_denied_without_key_valid_token_or_open_call(minted):
    with _client(key="") as client:
        token, _ = _open(client)
        assert client.post(f"/api/calls/{token}/session").status_code == 409
    with _client() as client:
        assert client.post("/api/calls/not-a-token/session").status_code == 404
        token = token_for(client.app.state.surface.call_tokens, DEMO_CASE_ID)
        client.app.state.surface.calls[token].status = "ready"
        assert client.post(f"/api/calls/{token}/session").status_code == 409


def test_tool_definitions_have_no_accept_tool():
    names = [t["name"] for t in webrtc.tool_definitions()]
    assert tuple(names) == CALL_TOOL_NAMES


def test_unknown_tool_is_refused():
    with _client() as client:
        token, room = _open(client)
        for name in ("accept_terms", "accept", "report_offered_terms2", ""):
            res = client.post(f"/api/calls/{token}/tool", json={"name": name, "call_id": "c1"})
            assert res.status_code == 403
        assert room.approval_status == "none"


def test_report_offered_terms_records_and_asks_the_family_once():
    with _client() as client:
        token, room = _open(client)
        args = json.dumps(
            {
                "months": 12,
                "monthly_price": "30",
                "number_kept": "kept",
                "voicemail_preserved": "kept",
            }
        )
        body = {"name": "report_offered_terms", "call_id": "c1", "arguments": args}
        res = client.post(f"/api/calls/{token}/tool", json=body)
        assert res.status_code == 200 and "Not accepted" in res.json()["output"]
        assert room.terms == OfferedTerms(12, "30", "kept", "kept")
        assert room.approval_status == "pending"
        # The same call id twice, or the same terms again, does not ask the family twice.
        client.post(f"/api/calls/{token}/tool", json=body)
        body["call_id"] = "c2"
        client.post(f"/api/calls/{token}/tool", json=body)
        asked = [t for t in room.turns if t.kind == "decision"]
        assert len(asked) == 1
        assert room.sentence is None and room.session.played == []


def test_bad_tool_arguments_are_refused():
    with _client() as client:
        token, room = _open(client)
        body = {"name": "report_offered_terms", "call_id": "c1", "arguments": "{}"}
        assert client.post(f"/api/calls/{token}/tool", json=body).status_code == 422
        assert room.terms is None


def test_other_tools_run_on_the_server():
    with _client() as client:
        token, room = _open(client)
        url = f"/api/calls/{token}/tool"
        res = client.post(url, json={"name": "get_request_and_conditions", "call_id": "r"})
        assert "Nothing has been accepted" in res.json()["output"]
        help_body = {"name": "request_human_help", "call_id": "h", "arguments": '{"reason": "x"}'}
        client.post(url, json=help_body)
        assert any(t.kind == "handoff" for t in room.turns)
        end_body = {"name": "end_call", "call_id": "e", "arguments": '{"reason": "done"}'}
        client.post(url, json=end_body)
        assert room.status == "ended"


def test_transcript_dedupes_by_item_and_trips_the_speech_check():
    with _client() as client:
        token, room = _open(client)
        ok = _say(client, token, "agent", "I'll check with the family.", "a1")
        assert ok.json()["tripped"] is False
        again = _say(client, token, "agent", "I'll check with the family.", "a1")
        assert again.json().get("duplicate") is True
        lines = [t for t in room.turns if t.who == "agent" and t.kind == "model"]
        assert len(lines) == 1 and lines[0].via == "realtime_voice"
        bad = _say(client, token, "agent", "Yes, we accept that offer.", "a2")
        assert bad.json()["tripped"] is True
        assert any(t.kind == "guard" for t in room.turns)
        assert not any("we accept" in t.text for t in room.turns if t.who == "agent")
        assert room.approval_status != "approved"


def test_rep_line_with_an_offer_is_detected_and_asks_the_family():
    with _client() as client:
        token, room = _open(client)
        assert _say(client, token, "rep", OFFER, "u1").status_code == 200
        assert room.terms == OfferedTerms(12, "30", "kept", "kept")
        assert room.approval_status == "pending"
        assert [t.via for t in room.turns if t.who == "rep"] == ["voice"]


def test_transcript_rejects_bad_input_and_unknown_tokens():
    with _client() as client:
        token, _ = _open(client)
        assert _say(client, token, "system", "x", "1").status_code == 422
        assert _say(client, token, "rep", "", "1").status_code == 422
        url = f"/api/calls/{token}/transcript"
        assert client.post(url, json={"who": "rep", "text": "hi"}).status_code == 422
        assert _say(client, "nope", "rep", "a", "1").status_code == 404
        assert client.post("/api/calls/nope/tool", json={"name": "end_call"}).status_code == 404


def test_approved_audio_plays_only_after_approval_and_a_hash_check(monkeypatch):
    async def fake_speak(settings, text):
        return "QUJD" if text else None

    monkeypatch.setattr(call_router, "speak_aloud", fake_speak)
    with _client() as client:
        token, room = _open(client)
        url = f"/api/calls/{token}/approved-audio"
        assert client.post(url).json()["played"] is False
        _say(client, token, "rep", OFFER, "u1")
        assert client.post(url).json()["played"] is False
        room.approve(room.terms_hash)
        res = client.post(url).json()
        assert res["played"] is True and res["text"] == build_acceptance_sentence(room.terms)
        assert res["audio"] == "QUJD"
        # A changed offer voids the approval before any more playback.
        _say(client, token, "rep", CHANGE, "u2")
        assert client.post(url).json()["played"] is False
