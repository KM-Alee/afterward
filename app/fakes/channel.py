"""Records outbound channel calls and injects inbound events after a signature check."""

import json
from collections.abc import Sequence

from app.contracts import (
    InboundEvent,
    Option,
    OptionRejected,
    WebhookRejected,
    WebhookRequest,
    validate_options,
)


class FakeChannel:
    """In-memory channel. `parse_webhook` requires header `X-Channel-Signature: ok`."""

    signature_header = "x-channel-signature"
    signature_value = "ok"

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.outbox: list[dict[str, object]] = []
        self._media: dict[str, tuple[bytes, str]] = {}
        self._inbound: list[InboundEvent] = []
        self._serial = 0

    def store_media(self, media_ref: str, data: bytes, mime: str) -> None:
        self._media[media_ref] = (data, mime)

    def inject(self, event: InboundEvent) -> None:
        self._inbound.append(event)

    async def send_text(self, to: str, text: str) -> str:
        return self._record("text", to, text=text)

    async def send_buttons(self, to: str, text: str, options: Sequence[Option]) -> str:
        try:
            validate_options(options)
        except OptionRejected:
            raise
        return self._record(
            "buttons", to, text=text, options=[item.model_dump() for item in options]
        )

    async def send_voice(self, to: str, ogg_opus: bytes) -> str:
        return self._record("voice", to, byte_length=len(ogg_opus))

    async def fetch_media(self, media_ref: str) -> tuple[bytes, str]:
        try:
            return self._media[media_ref]
        except KeyError:
            raise WebhookRejected("Unknown media reference") from None

    def parse_webhook(self, request: WebhookRequest) -> list[InboundEvent]:
        signature = {key.lower(): value for key, value in request.headers.items()}
        if signature.get(self.signature_header) != self.signature_value:
            raise WebhookRejected("Webhook signature was not accepted")
        events = list(self._inbound)
        self._inbound.clear()
        if request.body:
            raw = json.loads(request.body)
            if isinstance(raw, list):
                events.extend(InboundEvent.model_validate(item) for item in raw)
        return events

    def _record(self, kind: str, to: str, **payload: object) -> str:
        self._serial += 1
        message_id = f"{self.name}-{self._serial}"
        self.outbox.append({"id": message_id, "kind": kind, "to": to, **payload})
        return message_id
