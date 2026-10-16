"""In-memory call session. Acceptance audio plays only when the server asks."""

from collections.abc import AsyncIterator

from app.contracts import CallEvent, CallSessionError, CallTransport, json_payload


class FakeCallSession:
    """Browser or phone transport double. It has no accept method."""

    def __init__(self) -> None:
        self.transport: CallTransport | None = None
        self.started = False
        self.stopped = False
        self.audio_in: list[bytes] = []
        self.typed_turns: list[str] = []
        self.suspended = False
        self.played: list[str] = []
        self.discarded: list[str] = []
        self._queued: list[str] = []
        self._audio_out: list[bytes] = []
        self._events: list[CallEvent] = []

    async def start(self, transport: CallTransport) -> None:
        self.transport = transport
        self.started = True
        self.stopped = False

    async def stop(self) -> None:
        self._require_started()
        self.stopped = True

    async def relay_audio_in(self, pcm: bytes) -> None:
        self._require_open()
        self.audio_in.append(pcm)

    def queue_audio_out(self, pcm: bytes) -> None:
        self._audio_out.append(pcm)

    async def relay_audio_out(self) -> AsyncIterator[bytes]:
        self._require_open()
        while self._audio_out:
            yield self._audio_out.pop(0)

    async def send_typed_turn(self, text: str) -> None:
        self._require_open()
        self.typed_turns.append(text)

    async def suspend_acceptance(self) -> None:
        self._require_open()
        self.suspended = True

    async def resume_acceptance(self) -> None:
        self._require_open()
        self.suspended = False
        self.played.extend(self._queued)
        self._queued.clear()

    async def play_approved_sentence(self, sentence: str) -> None:
        """Queue the server-built sentence while suspended. Play it immediately otherwise."""
        self._require_open()
        if self.suspended:
            self._queued.append(sentence)
            return
        self.played.append(sentence)

    async def discard_queued_acceptance(self) -> None:
        """Drop audio that must not be played because the terms changed."""
        self._require_open()
        self.discarded.extend(self._queued)
        self._queued.clear()

    def push_event(self, event: CallEvent) -> None:
        event = CallEvent(kind=event.kind, payload=json_payload(dict(event.payload)))
        self._events.append(event)

    def events(self) -> tuple[CallEvent, ...]:
        return tuple(self._events)

    def _require_started(self) -> None:
        if not self.started:
            raise CallSessionError("The call session has not been started")

    def _require_open(self) -> None:
        self._require_started()
        if self.stopped:
            raise CallSessionError("The call session is stopped")
