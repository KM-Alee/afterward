"""Recorded Telegram payloads, the secret header, polling and media calls."""

import json

import pytest

from app.channels.transport import HttpResult, MemoryTransport
from app.contracts import (
    Channel,
    InboundKind,
    Option,
    OptionRejected,
    WebhookRejected,
    WebhookRequest,
)
from tests.channels.support import TELEGRAM_SECRET, load_payload, ok_telegram, telegram


def _request(name: str, *, secret: str | None = TELEGRAM_SECRET) -> WebhookRequest:
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return WebhookRequest(body=load_payload(name), headers=headers, query={})


def test_telegram_matches_channel_protocol():
    assert isinstance(telegram(), Channel)


def test_recorded_payloads_parse():
    channel = telegram()
    text = channel.parse_webhook(_request("telegram_text.json"))
    assert text[0].kind is InboundKind.text
    assert text[0].sender == "1001"
    assert text[0].text == "Hello from the demo"

    voice = channel.parse_webhook(_request("telegram_voice.json"))
    assert voice[0].kind is InboundKind.voice
    assert voice[0].media_ref == "voice-file-1"

    photo = channel.parse_webhook(_request("telegram_photo.json"))
    assert photo[0].kind is InboundKind.photo
    assert photo[0].media_ref == "photo-large"
    assert photo[0].text == "FICTIONAL DEMO bill"

    document = channel.parse_webhook(_request("telegram_document.json"))
    assert document[0].kind is InboundKind.document
    assert document[0].media_ref == "doc-file-1"

    button = channel.parse_webhook(_request("telegram_callback.json"))
    assert button[0].kind is InboundKind.button
    assert button[0].button_id == "confirm_intake"
    assert channel.pending_callback_ids == ["cbq-1"]


def test_bad_signature_produces_no_events():
    channel = telegram()
    events = None
    with pytest.raises(WebhookRejected):
        events = channel.parse_webhook(_request("telegram_callback.json", secret="wrong-secret"))
    assert events is None
    assert channel.pending_callback_ids == []


def test_missing_secret_and_empty_configuration_are_rejected():
    channel = telegram()
    with pytest.raises(WebhookRejected):
        channel.parse_webhook(_request("telegram_text.json", secret=None))
    closed = telegram(secret="")
    with pytest.raises(WebhookRejected):
        closed.parse_webhook(_request("telegram_text.json", secret=""))


def test_invalid_json_with_a_good_secret_produces_no_events():
    channel = telegram()
    events = None
    with pytest.raises(WebhookRejected):
        events = channel.parse_webhook(
            WebhookRequest(
                body=b"{",
                headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_SECRET},
                query={},
            )
        )
    assert events is None
    assert channel.pending_callback_ids == []


@pytest.mark.asyncio
async def test_inline_keyboard_uses_short_callback_data_and_answers():
    transport = MemoryTransport()
    channel = telegram(transport)
    long_id = "n" * 61
    options = [
        Option(id="confirm_intake", label="That's right"),
        Option(id=long_id, label="Fix something"),
    ]
    await channel.send_buttons("1001", "Please confirm", options)
    body = transport.calls[0].json_body
    assert isinstance(body, dict)
    row = body["reply_markup"]["inline_keyboard"][0]
    assert len(row) == 2
    for button in row:
        assert len(button["callback_data"].encode()) <= 64
        assert button["callback_data"].startswith("d:")
    channel.parse_webhook(_request("telegram_callback.json"))
    answered = await channel.answer_callbacks()
    assert answered == ["cbq-1"]
    assert transport.calls[-1].json_body == {"callback_query_id": "cbq-1"}


@pytest.mark.asyncio
async def test_four_buttons_are_rejected():
    channel = telegram()
    options = [Option(id=str(index), label=f"Choice {index}") for index in range(4)]
    with pytest.raises(OptionRejected):
        await channel.send_buttons("1001", "Too many", options)


@pytest.mark.asyncio
async def test_show_typing_posts_a_chat_action():
    transport = MemoryTransport()
    channel = telegram(transport)
    await channel.show_typing("1001")
    assert transport.calls[0].json_body == {"chat_id": "1001", "action": "typing"}


@pytest.mark.asyncio
async def test_send_voice_is_ogg_and_get_file_downloads():
    transport = MemoryTransport()
    channel = telegram(transport)
    await channel.send_voice("1001", b"opus-bytes")
    voice_call = transport.calls[0]
    assert voice_call.files is not None
    assert voice_call.files["voice"][2] == "audio/ogg"
    assert voice_call.files["voice"][1] == b"opus-bytes"

    transport.when(
        "GET",
        "getFile",
        HttpResult(
            status=200,
            body=json.dumps({"ok": True, "result": {"file_path": "voice/note.ogg"}}).encode(),
        ),
    )
    transport.when("GET", "/file/bot", HttpResult(status=200, body=b"downloaded-ogg"))
    data, mime = await channel.fetch_media("voice-file-1")
    assert data == b"downloaded-ogg"
    assert mime == "audio/ogg"


@pytest.mark.asyncio
async def test_polling_fallback_reads_updates_and_answers():
    transport = MemoryTransport()
    channel = telegram(transport)
    channel.mode = "polling"
    transport.when(
        "GET",
        "getUpdates",
        HttpResult(status=200, body=load_payload("telegram_updates.json")),
    )
    events, offset = await channel.poll_updates()
    assert events[0].kind is InboundKind.button
    assert events[0].button_id == "approve_plan"
    assert offset == 8
    assert any(
        isinstance(call.json_body, dict) and call.json_body.get("callback_query_id") == "cbq-poll"
        for call in transport.calls
    )
    assert ok_telegram().status == 200
