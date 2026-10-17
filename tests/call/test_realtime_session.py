"""OpenAIRealtimeSession on an injected fake transport. No network, no model."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.call import tools
from app.call.acceptance import CallRoom, OfferedTerms, build_acceptance_sentence
from app.call.realtime_session import OpenAIRealtimeSession, realtime_allowed
from app.config import Settings
from app.contracts import (
    CallEventKind,
    CallSessionError,
    CallTransport,
    ContractError,
    make_call_agent,
)
from app.web.factory import create_surface_app
from app.web.state import DEMO_CASE_ID
from tests.web.conftest import token_for


class FakeRealtime:
    """Stands in for the SDK RealtimeSession: an async-iterable of events."""

    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()
        self.audio: list[bytes] = []
        self.messages: list[str] = []
        self.approved: list[str] = []
        self.rejected: list[str] = []
        self.interrupts = 0
        self.closed = False

    def feed(self, **fields) -> None:
        self.q.put_nowait(SimpleNamespace(**fields))

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.q.get()

    async def send_audio(self, audio, *, commit=False):
        self.audio.append(audio)

    async def send_message(self, text):
        self.messages.append(text)

    async def interrupt(self):
        self.interrupts += 1

    async def approve_tool_call(self, call_id):
        self.approved.append(call_id)

    async def reject_tool_call(self, call_id, **_):
        self.rejected.append(call_id)

    async def close(self):
        self.closed = True


def _msg(role, text, item_id, status="completed"):
    return SimpleNamespace(
        type="message",
        role=role,
        item_id=item_id,
        status=status,
        content=[SimpleNamespace(text=None, transcript=text)],
    )


async def _make(speak=None):
    rt = FakeRealtime()

    async def factory():
        return rt

    async def say(sentence):
        return b"pcm:" + sentence.encode()

    session = OpenAIRealtimeSession(realtime_factory=factory, speak=speak or say)
    room = CallRoom(session=session)
    session.attach_room(room)
    return rt, session, room


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


async def test_lifecycle_audio_and_typed_turn():
    rt, session, room = await _make()
    await room.start()
    assert session.started and room.status == "live"
    await session.relay_audio_in(b"\x01\x02")
    await session.send_typed_turn("hello")
    assert rt.audio == [b"\x01\x02"] and rt.messages == ["hello"]
    rt.feed(type="audio", audio=SimpleNamespace(data=b"abc"))
    await _settle()
    chunks = [c async for c in session.relay_audio_out()]
    assert chunks == [b"abc"]
    assert any(e.kind is CallEventKind.latency for e in session.events())
    await session.stop()
    assert session.stopped and rt.closed
    with pytest.raises(CallSessionError):
        await session.relay_audio_in(b"x")


async def test_phone_transport_refused():
    _, session, _ = await _make()
    with pytest.raises(CallSessionError):
        await session.start(CallTransport.phone)


def test_accept_tool_still_rejected():
    class AcceptTool:
        name = "accept_terms"

    with pytest.raises(ContractError):
        make_call_agent(name="x", instructions="x", tools=[AcceptTool()])
    assert all("accept" not in t.name for t in tools.call_tools())


async def test_only_listed_tools_are_approved():
    rt, session, room = await _make()
    await room.start()
    rt.feed(
        type="tool_approval_required",
        call_id="c1",
        tool=SimpleNamespace(name="request_family_decision"),
    )
    rt.feed(type="tool_approval_required", call_id="c2", tool=SimpleNamespace(name="accept_terms"))
    await _settle()
    assert rt.approved == ["c1"] and rt.rejected == ["c2"]


async def test_terms_offered_event_from_tool_end():
    rt, session, room = await _make()
    await room.start()
    args = {
        "months": 12,
        "monthly_price": "30",
        "number_kept": "kept",
        "voicemail_preserved": "kept",
    }
    rt.feed(
        type="tool_end",
        tool=SimpleNamespace(name="report_offered_terms"),
        arguments=json.dumps(args),
    )
    await _settle()
    offered = [e for e in session.events() if e.kind is CallEventKind.terms_offered]
    assert offered and offered[0].payload["months"] == 12


async def test_approved_sentence_only_exact_text_and_queued_while_suspended():
    spoken: list[str] = []

    async def say(sentence):
        spoken.append(sentence)
        return b"pcm"

    rt, session, room = await _make(say)
    await room.start()
    terms = OfferedTerms(12, "30", "kept", "kept")
    digest = await room.report_offered_terms(terms)
    room.approve(digest)
    await room.on_representative_speech()
    await room.queue_acceptance()
    assert spoken == [] and session.played == []
    assert await room.try_play_acceptance() is True
    assert spoken == [build_acceptance_sentence(terms)]
    assert session.played == spoken
    assert [c async for c in session.relay_audio_out()] == [b"pcm"]
    # The model's words never reach the speaker as acceptance.
    assert rt.messages == []


async def test_changed_terms_discard_queued_sentence():
    spoken: list[str] = []

    async def say(sentence):
        spoken.append(sentence)
        return b"pcm"

    _, session, room = await _make(say)
    await room.start()
    digest = await room.report_offered_terms(OfferedTerms(12, "30", "kept", "kept"))
    room.approve(digest)
    await room.on_representative_speech()
    await room.queue_acceptance()
    await room.report_offered_terms(OfferedTerms(12, "35", "kept", "kept"))
    assert await room.try_play_acceptance() is False
    assert spoken == [] and session.discarded


async def test_guardrail_trip_suspends_and_discards_acceptance():
    rt, session, room = await _make()
    await room.start()
    digest = await room.report_offered_terms(OfferedTerms(12, "30", "kept", "kept"))
    room.approve(digest)
    await room.on_representative_speech()
    await room.queue_acceptance()
    rt.feed(type="audio", audio=SimpleNamespace(data=b"zzz"))
    rt.feed(type="guardrail_tripped", message="We accept those terms.")
    await _settle()
    assert session.suspended is True
    assert session.discarded and session.played == []
    assert rt.interrupts == 1
    assert [c async for c in session.relay_audio_out()] == []
    assert any(e.kind is CallEventKind.guardrail_tripped for e in session.events())
    assert room.guard_trips and room.acceptance_played is False


async def test_commitment_in_transcript_trips_even_without_sdk_event():
    rt, session, room = await _make()
    await room.start()
    rt.feed(type="history_updated", history=[_msg("assistant", "Agreed, go ahead.", "a1")])
    rt.feed(
        type="history_updated", history=[_msg("assistant", "Thanks, I will ask the family.", "a2")]
    )
    await _settle()
    assert room.guard_trips == ["commitment"]
    kinds = [(t.who, t.kind) for t in room.turns]
    assert ("agent", "model") in kinds and ("system", "guard") in kinds
    assert room.turns[-1].via == "realtime" or room.turns[-1].who == "agent"


async def test_interruption_clears_audio():
    rt, session, room = await _make()
    await room.start()
    rt.feed(type="audio", audio=SimpleNamespace(data=b"a"))
    rt.feed(type="audio_interrupted")
    await _settle()
    assert [c async for c in session.relay_audio_out()] == []
    assert any(e.kind is CallEventKind.audio_interrupted for e in session.events())


def test_realtime_allowed_needs_key():
    assert not realtime_allowed(None)
    assert not realtime_allowed(Settings())
    assert realtime_allowed(Settings(openai_api_key=SecretStr("sk-test")))


def test_ws_rehearsal_without_key_and_dial_blocked():
    app = create_surface_app(demo_passcode="fixture-passcode")
    with TestClient(app) as client:
        surface = client.app.state.surface
        token = token_for(surface.call_tokens, DEMO_CASE_ID)
        with client.websocket_connect(f"/ws/calls/{token}") as ws:
            ready = ws.receive_json()
            assert ready["mode"] == "rehearsal"
            assert ready["label"] == "rehearsal (no model)"
            assert ready["phone"] is False
            ws.send_bytes(b"\x00\x01")
        room = surface.calls[token]
        assert room.mode == "rehearsal"
        assert any(t.kind == "mode" and "rehearsal (no model)" in t.text for t in room.turns)
        refused = client.post(f"/api/calls/{token}/dial")
        assert refused.status_code == 403
        assert "not a phone call" in refused.text


async def test_request_tool_reads_plan_or_marks_scripted():
    _, session, room = await _make()
    tools.bind_room(room)
    scripted = json.loads(await tools.read_request_and_conditions(room))
    assert scripted["via"] == "scripted" and "line 4417" in scripted["request"]
    room.request_provider = lambda: "Close the Orbit account for Amina."
    planned = json.loads(await tools.read_request_and_conditions(room))
    assert planned["via"] == "plan" and "Orbit" in planned["request"]
    assert room.request_via == "plan"
    room.request_provider = lambda: None
    again = json.loads(await tools.read_request_and_conditions(room))
    assert again["via"] == "scripted"


class _EndingRealtime(FakeRealtime):
    """A model connection that closes after the queued events."""

    async def __anext__(self):
        if self.q.empty():
            raise StopAsyncIteration
        return await self.q.get()


async def test_a_bad_event_does_not_stop_the_call_and_counts_are_kept():
    rt, session, room = await _make()
    await session.start(CallTransport.browser)
    rt.feed(type="history_updated", history=None)  # tolerated
    rt.feed(type="tool_end", tool=None, arguments="{not json")  # handled, not fatal
    rt.feed(type="audio", audio=SimpleNamespace(data=b"\x01\x00"))
    await session.relay_audio_in(b"\x00" * 64)
    await _settle()
    assert session.stopped is False
    assert session.stats["audio_out_chunks"] == 1
    assert session.stats["audio_in_bytes"] == 64
    assert session.stats["connected"] is True


async def test_error_event_keeps_only_a_code():
    rt, session, _ = await _make()
    await session.start(CallTransport.browser)
    rt.feed(type="error", error={"type": "invalid_request_error", "message": "secret detail"})
    await _settle()
    assert session.stats["last_error"] == "invalid_request_error"
    assert "secret" not in str(session.stats)


async def test_dropped_connection_is_marked_lost_for_reconnect():
    rt = _EndingRealtime()

    async def factory():
        return rt

    session = OpenAIRealtimeSession(realtime_factory=factory, speak=None)
    await session.start(CallTransport.browser)
    await _settle()
    assert session.stopped is True and session.lost is True
    assert session.stats["connected"] is False


async def test_approved_sentence_is_never_recorded_twice():
    _, session, room = await _make()
    await room.start()
    terms = OfferedTerms(12, "30", "yes", "yes")
    await room.report_offered_terms(terms)
    room.approve(room.terms_hash)
    await room.queue_acceptance()
    assert await room.try_play_acceptance() is True
    assert await room.try_play_acceptance() is True
    said = [t for t in room.turns if t.kind == "template"]
    assert len(said) == 1
    assert session.played.count(room.sentence) == 1


async def test_live_captions_and_barge_in_from_the_model_stream():
    rt, session, _ = await _make()
    await session.start(CallTransport.browser)
    session._enqueue_audio(b"\x01\x00" * 10)

    def raw(**inner):
        return SimpleNamespace(type="raw_server_event", data=inner)

    rt.feed(type="raw_model_event", data=raw(type="input_audio_buffer.speech_started"))
    rt.feed(
        type="raw_model_event",
        data=raw(
            type="conversation.item.input_audio_transcription.delta", item_id="u1", delta="Hi"
        ),
    )
    rt.feed(
        type="raw_model_event",
        data=SimpleNamespace(type="transcript_delta", item_id="a1", delta="Hello", response_id="r"),
    )
    rt.feed(
        type="raw_model_event",
        data=raw(
            type="response.done",
            response={"status": "failed", "status_details": {"error": {"code": "rate_limited"}}},
        ),
    )
    await _settle()
    kinds = [(f["kind"], f.get("who"), f.get("state")) for f in session.live]
    assert ("speech", "rep", "start") in kinds
    assert ("caption", "rep", None) in kinds and ("caption", "agent", None) in kinds
    assert session._audio.empty()  # barge-in dropped the queued agent audio
    assert session.stats["last_error"] == "rate_limited"


async def test_interrupt_stops_the_agent():
    rt, session, _ = await _make()
    await session.start(CallTransport.browser)
    session._enqueue_audio(b"\x01\x00" * 10)
    await session.interrupt()
    assert rt.interrupts == 1
    assert session._audio.empty()
