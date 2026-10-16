"""Telegram turns reach the conversation. Delivery failures stay inside the handler."""

from datetime import date

from app.contracts import InboundEvent, InboundKind
from app.conversation.session import Outbound
from app.runtime import _conversation, replies_for


class _Conversation:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def handle_text(self, sender: str, text: str) -> list[Outbound]:
        self.calls.append(("text", text))
        return [Outbound(sender, "noted")]

    async def handle_button(self, sender: str, button_id: str) -> list[Outbound]:
        self.calls.append(("button", button_id))
        return [Outbound(sender, "pressed")]

    async def handle_voice(self, sender: str, ogg: bytes) -> list[Outbound]:
        self.calls.append(("voice", str(len(ogg))))
        return [Outbound(sender, "heard")]

    async def ingest_picture(self, **kwargs: object) -> None:
        self.calls.append(("photo", str(kwargs.get("mime"))))


class _Channel:
    def __init__(self, data: bytes, mime: str) -> None:
        self.data = data
        self.mime = mime

    async def fetch_media(self, media_ref: str) -> tuple[bytes, str]:
        assert media_ref == "file-1"
        return self.data, self.mime


def test_live_conversation_uses_the_malik_date():
    from app.config import Settings

    conversation = _conversation(Settings())
    assert conversation.case_date == date(2026, 3, 3)


async def test_text_button_and_voice_are_dispatched():
    conversation = _Conversation()
    channel = _Channel(b"ogg", "audio/ogg")
    text = await replies_for(
        conversation,
        channel,
        InboundEvent(kind=InboundKind.text, sender="1", text="hello"),
        cipher=None,
    )
    button = await replies_for(
        conversation,
        channel,
        InboundEvent(kind=InboundKind.button, sender="1", button_id="confirm_intake"),
        cipher=None,
    )
    voice = await replies_for(
        conversation,
        channel,
        InboundEvent(kind=InboundKind.voice, sender="1", media_ref="file-1"),
        cipher=None,
    )
    assert text[0].text == "noted"
    assert button[0].text == "pressed"
    assert voice[0].text == "heard"
    assert conversation.calls == [("text", "hello"), ("button", "confirm_intake"), ("voice", "3")]


async def test_non_image_file_is_not_stored():
    conversation = _Conversation()
    replies = await replies_for(
        conversation,
        _Channel(b"%PDF", "application/pdf"),
        InboundEvent(kind=InboundKind.document, sender="1", media_ref="file-1"),
        cipher=None,
    )
    assert "not a picture" in replies[0].text
    assert conversation.calls == []
