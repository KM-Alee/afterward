"""One gateway over Telegram and WhatsApp. Authenticity stays inside each adapter."""

from app.channels.telegram import TelegramChannel
from app.channels.whatsapp import WhatsAppChannel
from app.contracts import InboundEvent, Option, WebhookRequest


class ChannelGateway:
    """Dispatch by channel name. A rejected webhook raises and returns no events."""

    def __init__(
        self,
        *,
        telegram: TelegramChannel | None = None,
        whatsapp: WhatsAppChannel | None = None,
    ) -> None:
        self.telegram = telegram
        self.whatsapp = whatsapp

    def parse_webhook(self, channel: str, request: WebhookRequest) -> list[InboundEvent]:
        return self._adapter(channel).parse_webhook(request)

    async def ingest_webhook(self, channel: str, request: WebhookRequest) -> list[InboundEvent]:
        """Parse a webhook and, for Telegram, answer every callback query."""
        events = self.parse_webhook(channel, request)
        if channel == "telegram" and self.telegram is not None:
            await self.telegram.answer_callbacks()
        return events

    def verify_whatsapp(self, request: WebhookRequest) -> str:
        if self.whatsapp is None:
            raise RuntimeError("WhatsApp is not configured")
        return self.whatsapp.verify_challenge(request)

    async def poll_telegram(
        self, offset: int | None = None
    ) -> tuple[list[InboundEvent], int | None]:
        if self.telegram is None:
            raise RuntimeError("Telegram is not configured")
        return await self.telegram.poll_updates(offset)

    async def send_text(self, channel: str, to: str, text: str) -> str:
        return await self._adapter(channel).send_text(to, text)

    async def send_buttons(self, channel: str, to: str, text: str, options: list[Option]) -> str:
        return await self._adapter(channel).send_buttons(to, text, options)

    async def send_voice(self, channel: str, to: str, ogg_opus: bytes) -> str:
        return await self._adapter(channel).send_voice(to, ogg_opus)

    async def fetch_media(self, channel: str, media_ref: str) -> tuple[bytes, str]:
        return await self._adapter(channel).fetch_media(media_ref)

    def _adapter(self, channel: str) -> TelegramChannel | WhatsAppChannel:
        if channel == "telegram" and self.telegram is not None:
            return self.telegram
        if channel == "whatsapp" and self.whatsapp is not None:
            return self.whatsapp
        raise RuntimeError("That channel is not configured")
