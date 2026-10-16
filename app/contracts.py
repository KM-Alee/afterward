"""Shared interfaces for contract revision 1.

AI work is constructed with the OpenAI Agents SDK. Model output never adds a
recipient or grants a permission. `Clock.case_now` is synchronous. Mailbox,
channel sends, transcription, structured extraction, speech and the call
session are asynchronous. `EventBus.publish` joins the caller's transaction
and does not commit; subscribers run only after that transaction commits.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

CONTRACT_REVISION = 1

MAX_BUTTONS = 3
MAX_BUTTON_LABEL = 20

AIRole = Literal[
    "intake",
    "family_conversation",
    "dependency",
    "reply_reader",
    "document_reader",
]

JOB_KINDS = frozenset(
    {
        "inbox_poll",
        "send_request",
        "followup",
        "final_bill_check",
        "refund_evidence_check",
        "reconcile_action",
        "digest",
        "health_check",
    }
)

ACTION_KINDS = frozenset({"email_send", "calendar_insert", "chat_send", "handoff"})

CALL_TOOL_NAMES = (
    "get_request_and_conditions",
    "report_offered_terms",
    "request_family_decision",
    "request_human_help",
    "end_call",
)

APPROVAL_REQUIRED_CALL_TOOLS = frozenset({"request_family_decision"})

_FORBIDDEN_PAYLOAD_KEY = re.compile(
    r"(api_?key|token|secret|password|passcode|authorization|credential|vault|blob|document_body)",
    re.I,
)


class ContractError(Exception):
    """A deterministic contract failure. The message names the rule, not user data."""


class WebhookRejected(ContractError):
    """The transport could not authenticate the webhook. No events are returned."""


class OptionRejected(ContractError):
    """A button set breaks the three-option, twenty-character channel limit."""


class UnsafeEventPayload(ContractError):
    """An audit payload included a secret, a document body, or non-JSON data."""


class MailNotFound(ContractError):
    """The mailbox has no message for that id."""


class FakeFixtureMissing(ContractError):
    """A fake has no recorded model output for this input. It will not invent one."""


class CallSessionError(ContractError):
    """A call-session method was used in a state that cannot honour it."""


class Option(BaseModel):
    """One channel button. The label must fit a WhatsApp reply button."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=MAX_BUTTON_LABEL)


class InboundKind(StrEnum):
    text = "text"
    voice = "voice"
    photo = "photo"
    document = "document"
    button = "button"


class InboundEvent(BaseModel):
    """A normalised inbound turn. Authenticity is checked before this is built."""

    model_config = ConfigDict(extra="forbid")

    kind: InboundKind
    sender: str
    text: str | None = None
    media_ref: str | None = None
    button_id: str | None = None
    raw_id: str | None = None


@dataclass(frozen=True)
class WebhookRequest:
    """Transport bytes and headers. Body is not an instruction."""

    body: bytes
    headers: Mapping[str, str]
    query: Mapping[str, str]


@dataclass(frozen=True)
class ImageInput:
    """Image bytes for a vision schema. The mime type is a hint, not a permission."""

    data: bytes
    mime: str


class ChatMessage(BaseModel):
    """One model message. Content is data."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Transcript:
    """English transcript text. It does not by itself change a plan."""

    text: str
    language: str = "en"


@dataclass(frozen=True)
class SpeechChunk:
    """One chunk of synthesised audio for words the server already chose."""

    audio: bytes
    audio_format: str


class MailCursor(BaseModel):
    """A Gmail history cursor. `expired` asks the poller to fall back."""

    model_config = ConfigDict(extra="forbid")

    history_id: str | None = None
    expired: bool = False


class MailMessage(BaseModel):
    """A decoded message. Callers hash and strip; this object still has both texts."""

    model_config = ConfigDict(extra="forbid")

    mailbox: str
    gmail_id: str
    thread_id: str
    rfc_message_id: str
    from_addr: str
    from_name: str = ""
    reply_to: str | None = None
    to_addrs: list[str]
    subject: str
    latest_text: str
    full_text: str
    received_at: datetime
    references: list[str] = Field(default_factory=list)


class SendRequest(BaseModel):
    """An outbound mail request. The footer marker must already be in `text`."""

    model_config = ConfigDict(extra="forbid")

    mailbox: str
    to_addrs: list[str]
    subject: str
    text: str
    thread_id: str | None = None
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    from_name: str = ""
    footer_ref: str


class SentRecord(BaseModel):
    """A message observed in Sent, used to reconcile an uncertain action."""

    model_config = ConfigDict(extra="forbid")

    mailbox: str
    gmail_id: str
    thread_id: str
    rfc_message_id: str
    footer_ref: str
    text: str


class CallTransport(StrEnum):
    browser = "browser"
    phone = "phone"


class CallEventKind(StrEnum):
    transcript = "transcript"
    terms_offered = "terms_offered"
    guardrail_tripped = "guardrail_tripped"
    audio_interrupted = "audio_interrupted"
    latency = "latency"


@dataclass(frozen=True)
class CallEvent:
    """A call-room event. The payload follows the same secrecy rule as audit events."""

    kind: CallEventKind
    payload: Mapping[str, object]


@dataclass(frozen=True)
class EventRecord:
    """A committed audit event handed to subscribers. It is not an ORM row."""

    id: UUID
    case_id: UUID
    kind: str
    actor: str
    payload: dict[str, object]


class CaseClock(Protocol):
    """Anything with the demo clock offset. The ORM `Case` satisfies this."""

    clock_offset_s: int


def validate_options(options: Sequence[Option]) -> None:
    """Reject more than three buttons or a label that cannot fit the channel."""
    if len(options) > MAX_BUTTONS:
        raise OptionRejected("At most 3 options")
    for option in options:
        if len(option.label) > MAX_BUTTON_LABEL:
            raise OptionRejected("Option labels must be 20 characters or fewer")


def json_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Copy a JSON object and refuse secrets, document bodies and raw bytes."""
    try:
        encoded = json.dumps(payload)
    except TypeError:
        raise UnsafeEventPayload("Event payloads must be JSON objects") from None
    parsed = json.loads(encoded)
    if not isinstance(parsed, dict):
        raise UnsafeEventPayload("Event payloads must be JSON objects")
    _reject_forbidden_keys(parsed)
    return parsed


def _reject_forbidden_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _FORBIDDEN_PAYLOAD_KEY.search(str(key)):
                raise UnsafeEventPayload(
                    "Event payload keys cannot carry secrets or document bodies"
                )
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


def configure_agents_sdk(*, tracing: bool) -> None:
    """Enable or disable Agents SDK tracing. Sensitive data stays out of traces."""
    from agents import set_tracing_disabled

    set_tracing_disabled(not tracing)


def make_structured_agent(
    *,
    name: str,
    instructions: str,
    output_type: type[BaseModel],
    model: str,
):
    """Build an Agents SDK agent whose output must match `output_type`."""
    from agents import Agent

    return Agent(name=name, instructions=instructions, output_type=output_type, model=model)


def make_call_agent(*, name: str, instructions: str, tools: Sequence[object]):
    """Build a realtime call agent. An accept tool is rejected before construction."""
    from agents.realtime import RealtimeAgent

    for tool in tools:
        tool_name = str(getattr(tool, "name", ""))
        if "accept" in tool_name.lower():
            raise ContractError("Call agents cannot expose an accept tool")
    return RealtimeAgent(name=name, instructions=instructions, tools=list(tools))


@runtime_checkable
class Channel(Protocol):
    """One family channel. Webhook authenticity is checked inside `parse_webhook`."""

    async def send_text(self, to: str, text: str) -> str: ...

    async def send_buttons(self, to: str, text: str, options: Sequence[Option]) -> str: ...

    async def send_voice(self, to: str, ogg_opus: bytes) -> str: ...

    async def fetch_media(self, media_ref: str) -> tuple[bytes, str]: ...

    def parse_webhook(self, request: WebhookRequest) -> list[InboundEvent]: ...


@runtime_checkable
class Mailbox(Protocol):
    """Family or provider mailbox. `poll` falls back when the history cursor expired."""

    async def poll(
        self, mailbox: str, cursor: MailCursor | None
    ) -> tuple[list[MailMessage], MailCursor]: ...

    async def get(self, mailbox: str, gmail_id: str) -> MailMessage: ...

    async def send(self, request: SendRequest) -> SentRecord: ...

    async def search_sent(self, mailbox: str, footer_ref: str) -> SentRecord | None: ...


@runtime_checkable
class AIClient(Protocol):
    """Model access. Implemented on the Agents SDK. Results are proposals only."""

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str,
        prompt: str = "",
        keywords: Sequence[str] = (),
    ) -> Transcript: ...

    async def structured(
        self,
        role: AIRole,
        schema: type[BaseModel],
        messages: Sequence[ChatMessage],
        images: Sequence[ImageInput] | None = None,
    ) -> BaseModel: ...

    async def speak_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        audio_format: str = "pcm",
    ) -> AsyncIterator[SpeechChunk]: ...


@runtime_checkable
class Clock(Protocol):
    """Case time is the wall clock plus a demo-only offset. Leases do not use this."""

    def case_now(self, case: CaseClock) -> datetime: ...


@runtime_checkable
class CallSession(Protocol):
    """Realtime call engine over browser or phone. There is no accept method."""

    async def start(self, transport: CallTransport) -> None: ...

    async def stop(self) -> None: ...

    async def relay_audio_in(self, pcm: bytes) -> None: ...

    def relay_audio_out(self) -> AsyncIterator[bytes]: ...

    async def send_typed_turn(self, text: str) -> None: ...

    async def suspend_acceptance(self) -> None: ...

    async def resume_acceptance(self) -> None: ...

    async def play_approved_sentence(self, sentence: str) -> None: ...

    async def discard_queued_acceptance(self) -> None: ...

    def events(self) -> Sequence[CallEvent]: ...


@runtime_checkable
class EventBus(Protocol):
    """Persist an audit event in the caller's session and fan out after commit."""

    def publish(
        self,
        session: Session,
        case_id: UUID,
        kind: str,
        payload: Mapping[str, object],
        *,
        actor: str,
    ) -> EventRecord: ...

    def subscribe(self, case_id: UUID, callback: Callable[[EventRecord], None]) -> None: ...


class SqlEventBus:
    """Write `events` rows and notify subscribers only after the session commits."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, list[Callable[[EventRecord], None]]] = {}

    def subscribe(self, case_id: UUID, callback: Callable[[EventRecord], None]) -> None:
        self._subscribers.setdefault(case_id, []).append(callback)

    def publish(
        self,
        session: Session,
        case_id: UUID,
        kind: str,
        payload: Mapping[str, object],
        *,
        actor: str,
    ) -> EventRecord:
        from sqlalchemy import event as sa_event

        from app.models import Event

        safe = json_payload(payload)
        row = Event(case_id=case_id, kind=kind, actor=actor, payload=safe)
        session.add(row)
        session.flush()
        record = EventRecord(id=row.id, case_id=case_id, kind=kind, actor=actor, payload=safe)
        pending: list[EventRecord] = session.info.setdefault("afterward_pending_events", [])
        pending.append(record)
        if session.info.get("afterward_event_hook"):
            return record

        bus = self

        def _fanout(sess: Session) -> None:
            queued = list(sess.info.get("afterward_pending_events", []))
            sess.info["afterward_pending_events"] = []
            sess.info["afterward_event_hook"] = False
            for item in queued:
                for callback in bus._subscribers.get(item.case_id, []):
                    callback(item)

        def _drop(sess: Session) -> None:
            sess.info["afterward_pending_events"] = []
            sess.info["afterward_event_hook"] = False

        sa_event.listen(session, "after_commit", _fanout, once=True)
        sa_event.listen(session, "after_rollback", _drop, once=True)
        session.info["afterward_event_hook"] = True
        return record
