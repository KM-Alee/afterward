"""Shared fixtures for channel tests. Secrets here are fake and not credentials."""

import json
from pathlib import Path

from app.channels.telegram import TelegramChannel
from app.channels.transport import HttpResult, MemoryTransport
from app.channels.whatsapp import WhatsAppChannel

PAYLOADS = Path(__file__).parent / "payloads"
TELEGRAM_SECRET = "test-telegram-secret"
TELEGRAM_TOKEN = "test-bot-token"
WHATSAPP_TOKEN = "test-whatsapp-token"
WHATSAPP_APP_SECRET = "test-whatsapp-app-secret"
WHATSAPP_VERIFY = "test-whatsapp-verify"
PHONE_NUMBER_ID = "100000000000001"


def load_payload(name: str) -> bytes:
    return (PAYLOADS / name).read_bytes()


def ok_telegram() -> HttpResult:
    body = json.dumps({"ok": True, "result": {"message_id": 5}}).encode()
    return HttpResult(status=200, body=body)


def ok_whatsapp() -> HttpResult:
    body = json.dumps({"messages": [{"id": "wamid.out.1"}]}).encode()
    return HttpResult(status=200, body=body)


def telegram(
    transport: MemoryTransport | None = None, *, secret: str = TELEGRAM_SECRET
) -> TelegramChannel:
    client = transport or MemoryTransport()
    client.default(ok_telegram())
    return TelegramChannel(
        token=TELEGRAM_TOKEN,
        webhook_secret=secret,
        transport=client,
    )


def whatsapp(
    transport: MemoryTransport | None = None,
    *,
    clock=None,
    app_secret: str = WHATSAPP_APP_SECRET,
) -> WhatsAppChannel:
    client = transport or MemoryTransport()
    client.default(ok_whatsapp())
    return WhatsAppChannel(
        token=WHATSAPP_TOKEN,
        app_secret=app_secret,
        verify_token=WHATSAPP_VERIFY,
        phone_number_id=PHONE_NUMBER_ID,
        transport=client,
        clock=clock,
    )
