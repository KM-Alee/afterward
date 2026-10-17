"""Real CallSession on the Agents SDK realtime API. A browser call is not a phone call.

The model speaks and may call the five read/record tools. It has no accept tool. The only
acceptance audio is a server-built sentence, synthesised from exactly that text.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.call.guard import commitment_tripped
from app.call.tools import bind_room, build_call_agent
from app.contracts import (
    CALL_TOOL_NAMES,
    CallEvent,
    CallEventKind,
    CallSessionError,
    CallTransport,
    json_payload,
)

logger = logging.getLogger(__name__)

AUDIO_WAIT_S = 0.2
AUDIO_QUEUE_MAX = 512
RealtimeFactory = Callable[[], Awaitable[Any]]
SpeakFn = Callable[[str], Awaitable[bytes]]


def realtime_allowed(settings: Any) -> bool:
    """True when a key is set. Without one the room runs as a labelled rehearsal."""
    if settings is None:
        return False
    return bool(settings.openai_api_key.get_secret_value())


def _commitment_guardrail() -> Any:
    from agents import GuardrailFunctionOutput, OutputGuardrail

    async def _check(_ctx: Any, _agent: Any, output: Any) -> Any:
        return GuardrailFunctionOutput(
            output_info={"rule": "commitment"},
            tripwire_triggered=commitment_tripped(str(output)),
        )

    return OutputGuardrail(guardrail_function=_check, name="no_commitment")


def build_runner(settings: Any) -> Any:
    """Construct the SDK runner. Nothing connects until `run()` is awaited."""
    from agents.realtime import RealtimeRunner

    return RealtimeRunner(
        build_call_agent(),
        config={
            "model_settings": {
                "model_name": settings.realtime_model,
                "voice": settings.realtime_voice,
                "output_modalities": ["audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": settings.realtime_transcribe_model},
                # A fixed silence rule answers promptly; semantic detection can wait seconds.
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 550,
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output_guardrails": [_commitment_guardrail()],
            "guardrails_settings": {"debounce_text_length": 40},
        },
    )


async def _default_speak(settings: Any, sentence: str) -> bytes:
    from app.ai.client import AgentsSDKClient

    parts: list[bytes] = []
    async for chunk in AgentsSDKClient(settings).speak_stream(sentence, audio_format="pcm"):
        parts.append(chunk.audio)
    return b"".join(parts)


class OpenAIRealtimeSession:
    """Realtime voice session. `realtime_factory` and `speak` are injectable for tests."""

    def __init__(
        self,
        settings: Any = None,
        *,
        room: Any = None,
        realtime_factory: RealtimeFactory | None = None,
        speak: SpeakFn | None = None,
    ) -> None:
        self._settings = settings
        self.room = room
        self._factory = realtime_factory
        self._speak = speak
        self.transport: CallTransport | None = None
        self.started = False
        self.stopped = False
        self.suspended = False
        self.played: list[str] = []
        self.discarded: list[str] = []
        self._queued: list[str] = []
        self._events: list[CallEvent] = []
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(AUDIO_QUEUE_MAX)
        self._rt: Any = None
        self._task: asyncio.Task[None] | None = None
        self._seen_text: dict[str, str] = {}
        self._tripped: set[str] = set()
        self._turn_pending_since: float | None = None
        self._typed: list[str] = []  # typed lines already in the transcript
        # Counters the call page shows, so a silent call says where it stopped. No content.
        self.stats: dict[str, Any] = {
            "audio_in_bytes": 0,
            "audio_out_chunks": 0,
            "model_events": 0,
            "last_event": "",
            "last_error": "",
            "connected": False,
            "heard": 0,  # times the model detected the representative start speaking
            "turns_ended": 0,  # times it decided they had finished
            "transcribed": 0,
            "replies": 0,  # replies the model started
            "replies_done": 0,
            "replies_cut": 0,  # cancelled or cut off before finishing
            "guard_trips": 0,
            "last_reply_status": "",
        }
        self.on_event: Callable[[CallEvent], None] | None = None
        self.lost = False
        # Interface-only frames for the call page: live captions and who is speaking.
        # They carry no decisions; the transcript of record is the room's turns.
        self.live: list[dict[str, Any]] = []

    def attach_room(self, room: Any) -> None:
        self.room = room

    # lifecycle -----------------------------------------------------------------------
    async def start(self, transport: CallTransport) -> None:
        if transport is not CallTransport.browser:
            raise CallSessionError("Only the browser transport is available. No phone calls.")
        if self.started and not self.stopped:
            return
        factory = self._factory or self._sdk_factory
        self._rt = await factory()
        self.transport = transport
        self.started = True
        self.stopped = False
        self.lost = False
        self._task = asyncio.create_task(self._pump())

    async def _sdk_factory(self) -> Any:
        runner = build_runner(self._settings)
        key = self._settings.openai_api_key.get_secret_value()
        session = await runner.run(model_config={"api_key": key})
        return await session.__aenter__()

    async def stop(self) -> None:
        self._require_started()
        if self.stopped:
            return
        self.stopped = True
        task, self._task = self._task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        rt, self._rt = self._rt, None
        if rt is not None:
            with contextlib.suppress(Exception):
                await rt.close()

    # audio and turns -----------------------------------------------------------------
    async def relay_audio_in(self, pcm: bytes) -> None:
        self._require_open()
        self.stats["audio_in_bytes"] += len(pcm)
        await self._rt.send_audio(pcm)

    async def relay_audio_out(self) -> AsyncIterator[bytes]:
        """Yield audio that is ready, waiting briefly for more. Ends on a quiet gap or stop."""
        while True:
            try:
                yield await asyncio.wait_for(self._audio.get(), AUDIO_WAIT_S)
            except TimeoutError:
                return

    async def send_typed_turn(self, text: str) -> None:
        self._require_open()
        self._turn_pending_since = time.monotonic()
        self._typed.append(" ".join(text.split()))
        await self._rt.send_message(text)

    # acceptance ----------------------------------------------------------------------
    async def suspend_acceptance(self) -> None:
        self._require_open()
        self.suspended = True

    async def resume_acceptance(self) -> None:
        self._require_open()
        self.suspended = False
        queued, self._queued = self._queued, []
        for sentence in queued:
            await self._speak_sentence(sentence)

    async def play_approved_sentence(self, sentence: str) -> None:
        """Say exactly this server sentence. Queued while suspended."""
        self._require_open()
        if self.suspended:
            self._queued.append(sentence)
            return
        await self._speak_sentence(sentence)

    async def discard_queued_acceptance(self) -> None:
        self._require_open()
        self.discarded.extend(self._queued)
        self._queued.clear()

    async def _speak_sentence(self, sentence: str) -> None:
        """Synthesise the exact text. The model writes none of it."""
        try:
            if self._speak is not None:
                audio = await self._speak(sentence)
            else:
                audio = await _default_speak(self._settings, sentence)
        except Exception:
            logger.info("approved sentence", extra={"kind": "call.tts", "ok": False})
            raise CallSessionError("The approved sentence could not be spoken") from None
        self.played.append(sentence)
        self._enqueue_audio(audio)

    # events --------------------------------------------------------------------------
    def events(self) -> tuple[CallEvent, ...]:
        return tuple(self._events)

    def push_event(self, event: CallEvent) -> None:
        event = CallEvent(kind=event.kind, payload=json_payload(dict(event.payload)))
        self._events.append(event)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                logger.info("call event hook", extra={"kind": "call.hook", "ok": False})

    def _enqueue_audio(self, pcm: bytes) -> None:
        if not pcm:
            return
        if self._audio.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._audio.get_nowait()
        self._audio.put_nowait(pcm)

    def _clear_audio(self) -> None:
        while not self._audio.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._audio.get_nowait()

    async def _pump(self) -> None:
        """Read model events until the connection ends. One bad event never stops the call."""
        if self.room is not None:
            bind_room(self.room)
        self.stats["connected"] = True
        try:
            async for event in self._rt:
                self.stats["model_events"] += 1
                self.stats["last_event"] = str(getattr(event, "type", ""))[:40]
                try:
                    await self._handle(event)
                except Exception as exc:
                    self.stats["last_error"] = type(exc).__name__
                    logger.info(
                        "realtime event",
                        extra={
                            "kind": "call.realtime_event",
                            "ok": False,
                            "error": type(exc).__name__,
                        },
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stats["last_error"] = type(exc).__name__
            logger.info(
                "realtime pump",
                extra={"kind": "call.realtime", "ok": False, "error": type(exc).__name__},
            )
        finally:
            self.stats["connected"] = False
        if not self.stopped:
            # The model connection ended on its own. Mark it so the room reconnects.
            self.stopped = True
            self.lost = True

    async def _handle(self, event: Any) -> None:
        kind = getattr(event, "type", "")
        if kind == "audio":
            self._note_latency()
            self.stats["audio_out_chunks"] += 1
            self._enqueue_audio(bytes(event.audio.data))
        elif kind == "audio_interrupted":
            self._clear_audio()
            self.push_event(CallEvent(CallEventKind.audio_interrupted, {}))
        elif kind == "guardrail_tripped":
            await self._trip(str(getattr(event, "message", "")), source="sdk")
        elif kind == "tool_approval_required":
            await self._decide_tool(event)
        elif kind == "tool_end":
            self._on_tool_end(event)
        elif kind == "history_updated":
            await self._on_history(getattr(event, "history", []))
        elif kind == "raw_model_event":
            self._on_raw(getattr(event, "data", None))
        elif kind == "error":
            self.stats["last_error"] = _error_code(getattr(event, "error", None))
            logger.info(
                "realtime error",
                extra={"kind": "call.realtime", "ok": False, "error": self.stats["last_error"]},
            )

    def _on_raw(self, data: Any) -> None:
        """Live captions and speaking state from the model's own stream."""
        kind = str(getattr(data, "type", ""))
        if kind == "transcript_delta":
            delta = str(getattr(data, "delta", "") or "")
            if delta:
                item = str(getattr(data, "item_id", ""))
                self.live.append({"kind": "caption", "who": "agent", "item": item, "delta": delta})
            return
        if kind != "raw_server_event":
            return
        inner = getattr(data, "data", None)
        if not isinstance(inner, dict):
            return
        server = str(inner.get("type", ""))
        if server == "input_audio_buffer.speech_started":
            self.stats["heard"] += 1
            self._clear_audio()  # barge-in: the representative talks over the agent
            self.live.append({"kind": "speech", "who": "rep", "state": "start"})
        elif server == "input_audio_buffer.speech_stopped":
            self.stats["turns_ended"] += 1
            self.live.append({"kind": "speech", "who": "rep", "state": "stop"})
        elif server == "conversation.item.input_audio_transcription.delta":
            delta = str(inner.get("delta") or "")
            if delta:
                item = str(inner.get("item_id", ""))
                self.live.append({"kind": "caption", "who": "rep", "item": item, "delta": delta})
        elif server == "conversation.item.input_audio_transcription.completed":
            self.stats["transcribed"] += 1
        elif server == "conversation.item.input_audio_transcription.failed":
            self.stats["last_error"] = "transcription_failed"
        elif server == "response.created":
            self.stats["replies"] += 1
            self.live.append({"kind": "agent", "state": "thinking"})
        elif server == "response.done":
            response = inner.get("response") if isinstance(inner.get("response"), dict) else {}
            status = str(response.get("status") or "")
            self.stats["last_reply_status"] = status[:20]
            if status == "completed":
                self.stats["replies_done"] += 1
            elif status in {"cancelled", "incomplete"}:
                self.stats["replies_cut"] += 1
                details = response.get("status_details") or {}
                reason = details.get("reason") if isinstance(details, dict) else None
                if reason:
                    self.stats["last_reply_status"] = f"{status}:{reason}"[:40]
            if status == "failed":
                details = response.get("status_details") or {}
                error = details.get("error") if isinstance(details, dict) else None
                self.stats["last_error"] = _error_code(error or details or "response_failed")
            self.live.append({"kind": "agent", "state": "done"})
        elif server == "error":
            self.stats["last_error"] = _error_code(inner.get("error"))

    async def interrupt(self) -> None:
        """Stop the agent now: drop queued audio and cancel its current reply."""
        self._require_open()
        self._clear_audio()
        with contextlib.suppress(Exception):
            await self._rt.interrupt()

    async def _decide_tool(self, event: Any) -> None:
        """Approve the recording tool only. Anything off the contract list is rejected."""
        name = str(getattr(getattr(event, "tool", None), "name", ""))
        if name in CALL_TOOL_NAMES and "accept" not in name.lower():
            await self._rt.approve_tool_call(event.call_id)
        else:
            await self._rt.reject_tool_call(event.call_id)

    def _on_tool_end(self, event: Any) -> None:
        if str(getattr(getattr(event, "tool", None), "name", "")) != "report_offered_terms":
            return
        try:
            args = json.loads(getattr(event, "arguments", "") or "{}")
        except ValueError:
            args = {}
        payload = {
            "months": args.get("months"),
            "monthly_price": args.get("monthly_price"),
            "number_kept": args.get("number_kept"),
            "voicemail_preserved": args.get("voicemail_preserved"),
        }
        self.push_event(CallEvent(CallEventKind.terms_offered, payload))

    async def _on_history(self, history: Any) -> None:
        if not isinstance(history, list):
            return
        for item in history:
            role = getattr(item, "role", None)
            if getattr(item, "type", "") != "message" or role not in {"user", "assistant"}:
                continue
            text = _item_text(item)
            item_id = str(getattr(item, "item_id", ""))
            if not text or self._seen_text.get(item_id) == text:
                continue
            if role == "assistant" and getattr(item, "status", None) == "in_progress":
                continue
            self._seen_text[item_id] = text
            if role == "user":
                self._rep_line(text)
            else:
                await self._agent_line(text)

    def _rep_line(self, text: str) -> None:
        from app.call.acceptance import Turn

        norm = " ".join(text.split())
        if norm in self._typed:  # the model echoes typed lines back as user items
            self._typed.remove(norm)
            return
        self._turn_pending_since = time.monotonic()  # measured from the heard transcript

        if self.room is not None:
            self.room.turns.append(Turn(who="rep", text=text, via="voice"))
        self.push_event(CallEvent(CallEventKind.transcript, {"who": "rep", "text": text}))

    async def _agent_line(self, text: str) -> None:
        """Screen finished agent speech with the same check as the typed path."""
        if commitment_tripped(text):
            await self._trip(text, source="transcript")
            return
        if self.room is not None:
            await self.room.screen_model_speech(text)
            if self.room.turns and self.room.turns[-1].who == "agent":
                self.room.turns[-1].via = "realtime_voice"
        self.push_event(CallEvent(CallEventKind.transcript, {"who": "agent", "text": text}))

    async def _trip(self, text: str, *, source: str) -> None:
        """A possible agreement: stop playback, drop queued acceptance, suspend, record."""
        key = text.strip()
        if key in self._tripped:
            return
        self.stats["guard_trips"] += 1
        self._tripped.add(key)
        self.suspended = True
        self.discarded.extend(self._queued)
        self._queued.clear()
        self._clear_audio()
        if self._rt is not None:
            with contextlib.suppress(Exception):
                await self._rt.interrupt()
        self.push_event(
            CallEvent(CallEventKind.guardrail_tripped, {"rule": "commitment", "via": source})
        )
        room = self.room
        if room is None:
            return
        from app.call.acceptance import Turn

        room.guard_trips.append("commitment")
        room.acceptance_played = False
        room.turns.append(
            Turn(
                who="system",
                text=(
                    "The speech check stopped a possible agreement. "
                    "It reduces risk and is not a guarantee. Nothing was accepted."
                ),
                kind="guard",
            )
        )

    def _note_latency(self) -> None:
        started = self._turn_pending_since
        if started is None:
            return
        self._turn_pending_since = None
        elapsed = max(0, round((time.monotonic() - started) * 1000))
        if self.room is not None:
            turns = sum(1 for turn in self.room.turns if turn.who == "rep")
            self.room.latency.append({"turn": turns, "client_total_ms": elapsed, "via": "voice"})
        self.push_event(
            CallEvent(CallEventKind.latency, {"client_total_ms": elapsed, "via": "voice"})
        )

    def _require_started(self) -> None:
        if not self.started:
            raise CallSessionError("The call session has not been started")

    def _require_open(self) -> None:
        self._require_started()
        if self.stopped:
            raise CallSessionError("The call session is stopped")


def _error_code(error: Any) -> str:
    """A short code or type from a model error event. The message text is not kept."""
    for source in (error, getattr(error, "error", None)):
        if isinstance(source, dict):
            for key in ("code", "type"):
                if source.get(key):
                    return str(source[key])[:60]
        for key in ("code", "type"):
            value = getattr(source, key, None)
            if isinstance(value, str) and value:
                return value[:60]
    return "model_error"


def _item_text(item: Any) -> str:
    parts: list[str] = []
    for part in getattr(item, "content", None) or []:
        text = getattr(part, "text", None) or getattr(part, "transcript", None)
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return " ".join(parts)
