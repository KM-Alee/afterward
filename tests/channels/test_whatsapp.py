"""Recorded WhatsApp payloads, the hub signature, buttons, media and the 24-hour window."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.channels.errors import WindowClosed
from app.channels.transport import HttpResult, MemoryTransport
from app.channels.whatsapp import sign_body
from app.contracts import Channel, InboundKind, Option, WebhookRejected, WebhookRequest
from tests.channels.support import (
    PHONE_NUMBER_ID,
    WHATSAPP_APP_SECRET,
    WHATSAPP_TOKEN,
    WHATSAPP_VERIFY,
    load_payload,
    whatsapp,
)

SENDER = "15550001111"
OPENED = datetime.fromtimestamp(1710000000, tz=UTC)


def _request(
    name: str, *, secret: str = WHATSAPP_APP_SECRET, tamper: bool = False
) -> WebhookRequest:
    body = load_payload(name)
    signed = sign_body(body, secret)
    if tamper:
        body = body.replace(b"demo", b"xxxx", 1)
    return WebhookRequest(
        body=body,
        headers={"X-Hub-Signature-256": signed},
        query={},
    )


def test_whatsapp_matches_channel_protocol():
    assert isinstance(whatsapp(), Channel)


def test_raw_challenge_is_returned_unchanged():
    channel = whatsapp()
    challenge = channel.verify_challenge(
        WebhookRequest(
            body=b"",
            headers={},
            query={
                "hub.mode": "subscribe",
                "hub.verify_token": WHATSAPP_VERIFY,
                "hub.challenge": "12345abc",
            },
        )
    )
    assert challenge == "12345abc"
    with pytest.raises(WebhookRejected):
        channel.verify_challenge(
            WebhookRequest(
                body=b"",
                headers={},
                query={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "nope",
                    "hub.challenge": "12345abc",
                },
            )
        )


def test_recorded_payloads_parse():
    channel = whatsapp()
    text = channel.parse_webhook(_request("whatsapp_text.json"))
    assert text[0].kind is InboundKind.text
    assert text[0].sender == SENDER
    assert text[0].text == "Hello from the demo"

    button = channel.parse_webhook(_request("whatsapp_button.json"))
    assert button[0].kind is InboundKind.button
    assert button[0].button_id == "confirm_intake"

    audio = channel.parse_webhook(_request("whatsapp_audio.json"))
    assert audio[0].kind is InboundKind.voice
    assert audio[0].media_ref == "media-voice-1"

    image = channel.parse_webhook(_request("whatsapp_image.json"))
    assert image[0].kind is InboundKind.photo
    assert image[0].media_ref == "media-photo-1"

    document = channel.parse_webhook(_request("whatsapp_document.json"))
    assert document[0].kind is InboundKind.document
    assert document[0].media_ref == "media-doc-1"


def test_bad_signature_produces_no_events_and_no_window():
    channel = whatsapp()
    events = None
    with pytest.raises(WebhookRejected):
        events = channel.parse_webhook(_request("whatsapp_text.json", secret="other-secret"))
    assert events is None
    assert channel.last_inbound == {}
    with pytest.raises(WebhookRejected):
        channel.parse_webhook(_request("whatsapp_text.json", tamper=True))
    assert channel.last_inbound == {}


def test_empty_app_secret_rejects():
    channel = whatsapp(app_secret="")
    with pytest.raises(WebhookRejected):
        channel.parse_webhook(_request("whatsapp_text.json", secret=""))


@pytest.mark.asyncio
async def test_reply_buttons_are_capped():
    moment = {"at": OPENED + timedelta(hours=1)}
    transport = MemoryTransport()
    channel = whatsapp(transport, clock=lambda: moment["at"])
    channel.parse_webhook(_request("whatsapp_text.json"))
    options = [
        Option(id="approve_plan", label="Approve"),
        Option(id="change_plan", label="Change"),
        Option(id="not_now", label="Not now"),
    ]
    await channel.send_buttons(SENDER, "Please confirm", options)
    body = transport.calls[-1].json_body
    assert isinstance(body, dict)
    buttons = body["interactive"]["action"]["buttons"]
    assert len(buttons) == 3
    assert all(len(item["reply"]["title"]) <= 20 for item in buttons)
    assert body["to"] == SENDER
    assert PHONE_NUMBER_ID in transport.calls[-1].url


@pytest.mark.asyncio
async def test_window_guard_blocks_free_form_after_24_hours():
    moment = {"at": OPENED + timedelta(hours=23)}
    transport = MemoryTransport()
    channel = whatsapp(transport, clock=lambda: moment["at"])
    channel.parse_webhook(_request("whatsapp_text.json"))
    await channel.send_text(SENDER, "Inside the window")
    assert len(transport.calls) == 1
    moment["at"] = OPENED + timedelta(hours=24)
    with pytest.raises(WindowClosed):
        await channel.send_text(SENDER, "Too late")
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_media_download_uses_the_bearer_token():
    transport = MemoryTransport()
    channel = whatsapp(transport)
    transport.when(
        "GET",
        "media-voice-1",
        HttpResult(
            status=200,
            body=json.dumps(
                {"url": "https://lookaside.example/media/1", "mime_type": "audio/ogg"}
            ).encode(),
        ),
    )
    transport.when("GET", "lookaside.example", HttpResult(status=200, body=b"ogg-bytes"))
    data, mime = await channel.fetch_media("media-voice-1")
    assert data == b"ogg-bytes"
    assert mime == "audio/ogg"
    assert transport.calls[0].headers["Authorization"] == f"Bearer {WHATSAPP_TOKEN}"
    assert transport.calls[1].headers["Authorization"] == f"Bearer {WHATSAPP_TOKEN}"
