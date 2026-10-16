"""Telegram Bot API adapter. Webhooks check the secret header; polling is the fallback."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from app.channels.compare import header_value, secret_matches
from app.channels.errors import ChannelCallError
from app.channels.transport import HttpResult, MemoryTransport
from app.contracts import (
    InboundEvent,
    InboundKind,
    Option,
    WebhookRejected,
    WebhookRequest,
    validate_options,
)

CALLBACK_LIMIT = 64
_MIME_BY_SUFFIX = {
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


class Transport(Protocol):
    """The slice of HTTP the adapter uses."""

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


class TelegramChannel:
    """Verified Telegram updates, inline keyboards, file download and opus voice."""

    def __init__(
        self,
        *,
        token: str,
        webhook_secret: str,
        mode: str = "webhook",
        transport: Transport | None = None,
    ) -> None:
        self.mode = mode
        self._token = token
        self._webhook_secret = webhook_secret
        self._transport = transport or MemoryTransport()
        self._token_to_option: dict[str, str] = {}
        self.pending_callback_ids: list[str] = []

    def __repr__(self) -> str:
        return f"TelegramChannel(mode={self.mode})"

    async def show_typing(self, to: str) -> None:
        """Chat action while a voice note is being transcribed. It grants nothing."""
        await self._post("sendChatAction", {"chat_id": to, "action": "typing"})

    async def send_text(self, to: str, text: str) -> str:
        payload = await self._post("sendMessage", {"chat_id": to, "text": text})
        return _message_id(payload)

    async def send_buttons(self, to: str, text: str, options: Sequence[Option]) -> str:
        validate_options(options)
        keyboard = []
        for index, option in enumerate(options):
            token = self._callback_token(option, index)
            keyboard.append({"text": option.label, "callback_data": token})
        payload = await self._post(
            "sendMessage",
            {
                "chat_id": to,
                "text": text,
                "reply_markup": {"inline_keyboard": [keyboard]},
            },
        )
        return _message_id(payload)

    async def send_voice(self, to: str, ogg_opus: bytes) -> str:
        result = await self._transport.request(
            "POST",
            self._method_url("sendVoice"),
            data={"chat_id": to},
            files={"voice": ("note.ogg", ogg_opus, "audio/ogg")},
        )
        return _message_id(_json_object(result))

    async def fetch_media(self, media_ref: str) -> tuple[bytes, str]:
        meta = await self._get("getFile", {"file_id": media_ref})
        result = meta.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("file_path"), str):
            raise ChannelCallError("Telegram getFile did not return a file path")
        file_path = result["file_path"]
        download = await self._transport.request("GET", self._file_url(file_path))
        if download.status >= 400:
            raise ChannelCallError("Telegram file download failed")
        return download.body, _mime_for_path(file_path)

    def parse_webhook(self, request: WebhookRequest) -> list[InboundEvent]:
        """Reject a bad secret before any update is read. A failure returns no events."""
        provided = header_value(request.headers, "X-Telegram-Bot-Api-Secret-Token")
        if not secret_matches(provided, self._webhook_secret):
            raise WebhookRejected("Telegram webhook secret was not accepted")
        return self._events_from_body(request.body)

    async def poll_updates(
        self, offset: int | None = None
    ) -> tuple[list[InboundEvent], int | None]:
        """Polling fallback. The bot token authenticates getUpdates; there is no webhook header."""
        params: dict[str, str] = {"timeout": "0"}
        if offset is not None:
            params["offset"] = str(offset)
        payload = await self._get("getUpdates", params)
        updates = payload.get("result")
        if not isinstance(updates, list):
            raise ChannelCallError("Telegram getUpdates did not return a list")
        events: list[InboundEvent] = []
        next_offset = offset
        for update in updates:
            if not isinstance(update, dict):
                continue
            events.extend(self._events_from_update(update))
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                next_offset = update_id + 1
        await self.answer_callbacks()
        return events, next_offset

    async def answer_callbacks(self) -> list[str]:
        """answerCallbackQuery for every press parsed since the last call."""
        ids = list(self.pending_callback_ids)
        self.pending_callback_ids.clear()
        for callback_id in ids:
            await self._post("answerCallbackQuery", {"callback_query_id": callback_id})
        return ids

    def _events_from_body(self, body: bytes) -> list[InboundEvent]:
        if not body:
            return []
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebhookRejected("Telegram webhook body was not JSON") from exc
        if not isinstance(payload, dict):
            raise WebhookRejected("Telegram webhook body was not an update")
        return self._events_from_update(payload)

    def _events_from_update(self, update: Mapping[str, object]) -> list[InboundEvent]:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            return [self._button_event(callback)]
        message = update.get("message")
        if isinstance(message, dict):
            event = self._message_event(message)
            if event is not None:
                return [event]
        return []

    def _button_event(self, callback: Mapping[str, object]) -> InboundEvent:
        callback_id = callback.get("id")
        if isinstance(callback_id, str) and callback_id:
            self.pending_callback_ids.append(callback_id)
        raw = callback.get("data")
        data = raw if isinstance(raw, str) else ""
        sender = _user_id(callback.get("from"))
        return InboundEvent(
            kind=InboundKind.button,
            sender=sender,
            button_id=self._option_id(data),
            raw_id=callback_id if isinstance(callback_id, str) else None,
        )

    def _message_event(self, message: Mapping[str, object]) -> InboundEvent | None:
        sender = _user_id(message.get("from")) or _chat_id(message.get("chat"))
        raw_id = message.get("message_id")
        raw = str(raw_id) if isinstance(raw_id, int) else None
        caption = message.get("caption") if isinstance(message.get("caption"), str) else None
        if isinstance(message.get("text"), str):
            return InboundEvent(
                kind=InboundKind.text, sender=sender, text=message["text"], raw_id=raw
            )
        voice = message.get("voice")
        if isinstance(voice, dict) and isinstance(voice.get("file_id"), str):
            return InboundEvent(
                kind=InboundKind.voice,
                sender=sender,
                text=caption,
                media_ref=voice["file_id"],
                raw_id=raw,
            )
        photo = message.get("photo")
        if isinstance(photo, list) and photo:
            file_id = _largest_photo(photo)
            if file_id:
                return InboundEvent(
                    kind=InboundKind.photo,
                    sender=sender,
                    text=caption,
                    media_ref=file_id,
                    raw_id=raw,
                )
        document = message.get("document")
        if isinstance(document, dict) and isinstance(document.get("file_id"), str):
            return InboundEvent(
                kind=InboundKind.document,
                sender=sender,
                text=caption,
                media_ref=document["file_id"],
                raw_id=raw,
            )
        return None

    def _callback_token(self, option: Option, index: int) -> str:
        token = f"d:{option.id}:{index}"
        if len(token.encode()) > CALLBACK_LIMIT:
            digest = hashlib.sha256(option.id.encode()).hexdigest()[:16]
            token = f"d:{digest}:{index}"
        self._token_to_option[token] = option.id
        return token

    def _option_id(self, data: str) -> str:
        mapped = self._token_to_option.get(data)
        if mapped:
            return mapped
        parts = data.split(":")
        if len(parts) == 3 and parts[0] == "d" and parts[2].isdigit():
            return parts[1]
        return data

    async def _post(self, method: str, body: Mapping[str, object]) -> dict[str, object]:
        result = await self._transport.request(
            "POST", self._method_url(method), json_body=dict(body)
        )
        return _json_object(result)

    async def _get(self, method: str, params: Mapping[str, str]) -> dict[str, object]:
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = self._method_url(method)
        if query:
            url = f"{url}?{query}"
        result = await self._transport.request("GET", url)
        return _json_object(result)

    def _method_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _file_url(self, file_path: str) -> str:
        return f"https://api.telegram.org/file/bot{self._token}/{file_path}"


def _json_object(result: HttpResult) -> dict[str, object]:
    if result.status >= 400:
        raise ChannelCallError("Telegram API request failed")
    payload = result.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ChannelCallError("Telegram API response was not ok")
    return payload


def _message_id(payload: Mapping[str, object]) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and "message_id" in result:
        return str(result["message_id"])
    raise ChannelCallError("Telegram did not return a message id")


def _user_id(value: object) -> str:
    if isinstance(value, dict) and "id" in value:
        return str(value["id"])
    return ""


def _chat_id(value: object) -> str:
    if isinstance(value, dict) and "id" in value:
        return str(value["id"])
    return ""


def _largest_photo(photos: list[object]) -> str:
    best_id = ""
    best_size = -1
    for item in photos:
        if not isinstance(item, dict) or not isinstance(item.get("file_id"), str):
            continue
        size = item.get("file_size")
        if not isinstance(size, int):
            size = item.get("width") if isinstance(item.get("width"), int) else 0
        if size >= best_size:
            best_size = size
            best_id = item["file_id"]
    return best_id


def _mime_for_path(file_path: str) -> str:
    suffix = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
