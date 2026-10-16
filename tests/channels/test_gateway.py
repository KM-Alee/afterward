"""The gateway dispatches to the adapter that already checked authenticity."""

import pytest

from app.channels.gateway import ChannelGateway
from app.channels.whatsapp import sign_body
from app.contracts import InboundKind, WebhookRejected, WebhookRequest
from tests.channels.support import (
    WHATSAPP_APP_SECRET,
    WHATSAPP_VERIFY,
    load_payload,
    telegram,
    whatsapp,
)


def _gateway() -> ChannelGateway:
    return ChannelGateway(telegram=telegram(), whatsapp=whatsapp())


def test_bad_signature_on_either_channel_produces_no_events():
    gateway = _gateway()
    events = None
    with pytest.raises(WebhookRejected):
        events = gateway.parse_webhook(
            "telegram",
            WebhookRequest(body=load_payload("telegram_text.json"), headers={}, query={}),
        )
    assert events is None
    body = load_payload("whatsapp_text.json")
    with pytest.raises(WebhookRejected):
        events = gateway.parse_webhook(
            "whatsapp",
            WebhookRequest(
                body=body,
                headers={"X-Hub-Signature-256": sign_body(body, "wrong-secret")},
                query={},
            ),
        )
    assert events is None
    assert gateway.whatsapp is not None
    assert gateway.whatsapp.last_inbound == {}


@pytest.mark.asyncio
async def test_ingest_answers_a_telegram_callback_and_whatsapp_challenge_is_raw():
    gateway = _gateway()
    events = await gateway.ingest_webhook(
        "telegram",
        WebhookRequest(
            body=load_payload("telegram_callback.json"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-telegram-secret"},
            query={},
        ),
    )
    assert events[0].kind is InboundKind.button
    assert events[0].button_id == "confirm_intake"
    assert gateway.telegram is not None
    assert gateway.telegram.pending_callback_ids == []
    challenge = gateway.verify_whatsapp(
        WebhookRequest(
            body=b"",
            headers={},
            query={
                "hub.mode": "subscribe",
                "hub.verify_token": WHATSAPP_VERIFY,
                "hub.challenge": "raw-challenge",
            },
        )
    )
    assert challenge == "raw-challenge"
    assert WHATSAPP_APP_SECRET
