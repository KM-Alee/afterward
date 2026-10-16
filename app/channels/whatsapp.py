"""WhatsApp Cloud API adapter: challenge, HMAC signature, buttons, media and the 24-hour window."""

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.channels.compare import constant_time_eq, header_value, secret_matches
from app.channels.errors import ChannelCallError, WindowClosed
from app.channels.transport import HttpResult, MemoryTransport
from app.contracts import (
    InboundEvent,
    InboundKind,
    Option,
    WebhookRejected,
    WebhookRequest,
    validate_options,
)

GRAPH_VERSION = "v21.0"
WINDOW = timedelta(hours=24)
MAX_BODY = 1024


class Transport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        json_body: object = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
    ) -> HttpResult: ...


class WhatsAppChannel:
    """Task-scoped WhatsApp sends. Free-form messages stop when the 24-hour window closes."""

    def __init__(
        self,
        *,
        token: str,
        app_secret: str,
        verify_token: str,
        phone_number_id: str,
        transport: Transport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._token = token
        self._app_secret = app_secret
        self._verify_token = verify_token
        self._phone_number_id = phone_number_id
        self._transport = transport or MemoryTransport()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.last_inbound: dict[str, datetime] = {}

    def __repr__(self) -> str:
        return "WhatsAppChannel()"

    def verify_challenge(self, request: WebhookRequest) -> str:
        """Return the raw hub.challenge when the verify token matches."""
        mode = request.query.get("hub.mode", "")
        token = request.query.get("hub.verify_token", "")
        challenge = request.query.get("hub.challenge")
        if mode != "subscribe" or not secret_matches(token, self._verify_token):
            raise WebhookRejected("WhatsApp verification was not accepted")
        if challenge is None:
            raise WebhookRejected("WhatsApp verification was not accepted")
        return challenge

    def parse_webhook(self, request: WebhookRequest) -> list[InboundEvent]:
        """Check X-Hub-Signature-256 before reading the body. A bad signature yields no events."""
        provided = header_value(request.headers, "X-Hub-Signature-256")
        if not _signature_ok(request.body, provided, self._app_secret):
            raise WebhookRejected("WhatsApp signature was not accepted")
        return self._events_from_body(request.body)

    async def send_text(self, to: str, text: str) -> str:
        self._require_window(to)
        _require_body(text)
        payload = await self._post(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            }
        )
        return _message_id(payload)

    async def send_buttons(self, to: str, text: str, options: Sequence[Option]) -> str:
        self._require_window(to)
        validate_options(options)
        _require_body(text)
        buttons = [
            {"type": "reply", "reply": {"id": option.id, "title": option.label}}
            for option in options
        ]
        payload = await self._post(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text},
                    "action": {"buttons": buttons},
                },
            }
        )
        return _message_id(payload)

    async def send_voice(self, to: str, ogg_opus: bytes) -> str:
        self._require_window(to)
        media = await self._post_media(ogg_opus)
        media_id = media.get("id")
        if not isinstance(media_id, str):
            raise ChannelCallError("WhatsApp media upload did not return an id")
        payload = await self._post(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "audio",
                "audio": {"id": media_id},
            }
        )
        return _message_id(payload)

    async def fetch_media(self, media_ref: str) -> tuple[bytes, str]:
        meta_result = await self._transport.request(
            "GET",
            f"https://graph.facebook.com/{GRAPH_VERSION}/{media_ref}",
            headers=self._auth(),
        )
        meta = _json_dict(meta_result)
        url = meta.get("url")
        mime = meta.get("mime_type")
        if not isinstance(url, str):
            raise ChannelCallError("WhatsApp media lookup did not return a url")
        download = await self._transport.request("GET", url, headers=self._auth())
        if download.status >= 400:
            raise ChannelCallError("WhatsApp media download failed")
        return download.body, mime if isinstance(mime, str) else "application/octet-stream"

    def window_open(self, to: str, *, now: datetime | None = None) -> bool:
        last = self.last_inbound.get(to)
        if last is None:
            return False
        moment = now or self._clock()
        return moment - last < WINDOW

    def _require_window(self, to: str) -> None:
        if not self.window_open(to):
            raise WindowClosed(
                "Free-form WhatsApp messages need an inbound message within 24 hours"
            )

    def _events_from_body(self, body: bytes) -> list[InboundEvent]:
        if not body:
            return []
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebhookRejected("WhatsApp webhook body was not JSON") from exc
        if not isinstance(payload, dict):
            return []
        events: list[InboundEvent] = []
        entries = payload.get("entry")
        if not isinstance(entries, list):
            return []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if isinstance(value, dict):
                    events.extend(self._events_from_value(value))
        return events

    def _events_from_value(self, value: Mapping[str, object]) -> list[InboundEvent]:
        messages = value.get("messages")
        if not isinstance(messages, list):
            return []
        events: list[InboundEvent] = []
        for message in messages:
            if isinstance(message, dict):
                event = self._one_message(message)
                if event is not None:
                    events.append(event)
        return events

    def _one_message(self, message: Mapping[str, object]) -> InboundEvent | None:
        sender = message.get("from") if isinstance(message.get("from"), str) else ""
        raw_id = message.get("id") if isinstance(message.get("id"), str) else None
        self._note_inbound(sender, message.get("timestamp"))
        kind = message.get("type")
        if kind == "text":
            text = message.get("text")
            body = text.get("body") if isinstance(text, dict) else None
            return InboundEvent(
                kind=InboundKind.text,
                sender=sender,
                text=body if isinstance(body, str) else "",
                raw_id=raw_id,
            )
        if kind == "interactive":
            interactive = message.get("interactive")
            reply = interactive.get("button_reply") if isinstance(interactive, dict) else None
            button_id = reply.get("id") if isinstance(reply, dict) else None
            title = reply.get("title") if isinstance(reply, dict) else None
            return InboundEvent(
                kind=InboundKind.button,
                sender=sender,
                text=title if isinstance(title, str) else None,
                button_id=button_id if isinstance(button_id, str) else "",
                raw_id=raw_id,
            )
        if kind == "audio":
            return self._media_event(InboundKind.voice, message, "audio", sender, raw_id)
        if kind == "image":
            return self._media_event(InboundKind.photo, message, "image", sender, raw_id)
        if kind == "document":
            return self._media_event(InboundKind.document, message, "document", sender, raw_id)
        return None

    def _media_event(
        self,
        kind: InboundKind,
        message: Mapping[str, object],
        key: str,
        sender: str,
        raw_id: str | None,
    ) -> InboundEvent | None:
        media = message.get(key)
        if not isinstance(media, dict) or not isinstance(media.get("id"), str):
            return None
        caption = media.get("caption") if isinstance(media.get("caption"), str) else None
        return InboundEvent(
            kind=kind, sender=sender, text=caption, media_ref=media["id"], raw_id=raw_id
        )

    def _note_inbound(self, sender: str, timestamp: object) -> None:
        if not sender or not isinstance(timestamp, str) or not timestamp.isdigit():
            return
        moment = datetime.fromtimestamp(int(timestamp), tz=UTC)
        previous = self.last_inbound.get(sender)
        if previous is None or moment > previous:
            self.last_inbound[sender] = moment

    async def _post(self, body: Mapping[str, object]) -> dict[str, object]:
        result = await self._transport.request(
            "POST",
            self._messages_url(),
            headers=self._auth(),
            json_body=dict(body),
        )
        return _json_dict(result)

    async def _post_media(self, ogg_opus: bytes) -> dict[str, object]:
        result = await self._transport.request(
            "POST",
            f"https://graph.facebook.com/{GRAPH_VERSION}/{self._phone_number_id}/media",
            headers=self._auth(),
            data={"messaging_product": "whatsapp", "type": "audio/ogg"},
            files={"file": ("note.ogg", ogg_opus, "audio/ogg")},
        )
        return _json_dict(result)

    def _messages_url(self) -> str:
        return f"https://graph.facebook.com/{GRAPH_VERSION}/{self._phone_number_id}/messages"

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}


def sign_body(body: bytes, app_secret: str) -> str:
    """Build the X-Hub-Signature-256 header value for a raw body. Tests use a fake secret."""
    digest = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _signature_ok(body: bytes, header: str, app_secret: str) -> bool:
    if not app_secret:
        return False
    return constant_time_eq(header, sign_body(body, app_secret))


def _json_dict(result: HttpResult) -> dict[str, object]:
    if result.status >= 400:
        raise ChannelCallError("WhatsApp API request failed")
    payload = result.json()
    if not isinstance(payload, dict):
        raise ChannelCallError("WhatsApp API response was not an object")
    return payload


def _message_id(payload: Mapping[str, object]) -> str:
    messages = payload.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        message_id = messages[0].get("id")
        if isinstance(message_id, str):
            return message_id
    raise ChannelCallError("WhatsApp did not return a message id")


def _require_body(text: str) -> None:
    if len(text) > MAX_BODY:
        raise ChannelCallError("WhatsApp body is longer than 1024 characters")
