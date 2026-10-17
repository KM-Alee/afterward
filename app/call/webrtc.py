"""Browser-direct voice: mint a short-lived Realtime client secret on the server.

The browser talks to OpenAI over WebRTC with the ephemeral value. The long-lived API key
never leaves this process. There is no accept tool in the session. A browser call is not
a phone call.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.call.tools import CALL_INSTRUCTIONS
from app.contracts import CALL_TOOL_NAMES

logger = logging.getLogger(__name__)

CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
FALLBACK_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
EXPIRES_SECONDS = 600

# Tests substitute an httpx transport here. Production leaves it None.
_TRANSPORT: httpx.AsyncBaseTransport | None = None


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


_STR = {"type": "string"}
TOOL_SPECS: dict[str, dict] = {
    "get_request_and_conditions": _fn(
        "get_request_and_conditions",
        "Read the approved request and its conditions. Call before stating the request. "
        "This does not accept anything.",
        {},
        [],
    ),
    "report_offered_terms": _fn(
        "report_offered_terms",
        "Record terms the representative offered, exactly as said. This does not accept them.",
        {
            "months": {"type": "integer"},
            "monthly_price": {"type": "string", "description": "Dollars per month, e.g. 30"},
            "number_kept": {"type": "string", "description": "kept, not kept or not stated"},
            "voicemail_preserved": {
                "type": "string",
                "description": "kept, not kept or not stated",
            },
        },
        ["months", "monthly_price", "number_kept", "voicemail_preserved"],
    ),
    "request_family_decision": _fn(
        "request_family_decision",
        "Ask the family to decide. At most three options. Acceptance is never a tool result.",
        {
            "summary": _STR,
            "option_one": _STR,
            "option_two": _STR,
            "option_three": _STR,
        },
        ["summary", "option_one", "option_two", "option_three"],
    ),
    "request_human_help": _fn(
        "request_human_help",
        "The representative will only deal with a person. Hand the step back.",
        {"reason": _STR},
        ["reason"],
    ),
    "end_call": _fn(
        "end_call",
        "End the call politely, without agreeing to any terms. Only when it is clearly over.",
        {"reason": _STR},
        ["reason"],
    ),
}


def tool_definitions() -> list[dict]:
    """The five contract tools as Realtime function definitions. Never an accept tool."""
    if tuple(TOOL_SPECS) != CALL_TOOL_NAMES:
        raise RuntimeError("Call tools drifted from the contract list")
    if any("accept" in name for name in TOOL_SPECS):
        raise RuntimeError("An accept tool is not allowed")
    return [TOOL_SPECS[name] for name in CALL_TOOL_NAMES]


def build_session_config(settings: Any, *, transcribe_model: str | None = None) -> dict:
    """The Realtime session the browser will run. Contains no secret."""
    return {
        "type": "realtime",
        "model": settings.realtime_model,
        "instructions": CALL_INSTRUCTIONS,
        "audio": {
            "input": {
                "transcription": {
                    "model": transcribe_model or settings.realtime_transcribe_model,
                    "language": "en",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": int(getattr(settings, "realtime_silence_ms", 550)),
                    "interrupt_response": True,
                    "create_response": True,
                },
            },
            "output": {"voice": settings.realtime_voice},
        },
        "tools": tool_definitions(),
        "tool_choice": "auto",
    }


class SessionError(Exception):
    """Minting failed. `message` is safe to show: it never contains the key."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        err = body.get("error", body) if isinstance(body, dict) else {}
        text = str(err.get("message") or err.get("code") or "")[:300]
    except ValueError:
        text = ""
    return text or f"OpenAI answered {response.status_code}"


async def _post(settings: Any, config: dict) -> httpx.Response:
    key = settings.openai_api_key.get_secret_value()
    async with httpx.AsyncClient(timeout=15, transport=_TRANSPORT) as client:
        return await client.post(
            CLIENT_SECRETS_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "expires_after": {"anchor": "created_at", "seconds": EXPIRES_SECONDS},
                "session": config,
            },
        )


async def mint_client_secret(settings: Any) -> dict:
    """Mint an ephemeral client secret. Returns value, expires_at, model and a config echo."""
    if not settings.openai_api_key.get_secret_value():
        raise SessionError("No OpenAI key is configured. The room runs as a rehearsal.", 409)
    config = build_session_config(settings)
    try:
        response = await _post(settings, config)
        if (
            response.status_code == 400
            and settings.realtime_transcribe_model != FALLBACK_TRANSCRIBE_MODEL
            and "transcri" in _error_text(response).lower()
        ):
            config = build_session_config(settings, transcribe_model=FALLBACK_TRANSCRIBE_MODEL)
            response = await _post(settings, config)
    except httpx.HTTPError as exc:
        logger.info("client secret", extra={"kind": "call.session", "ok": False})
        raise SessionError(f"Could not reach OpenAI ({type(exc).__name__}).") from exc
    if response.status_code >= 400:
        logger.info(
            "client secret",
            extra={"kind": "call.session", "ok": False, "status": response.status_code},
        )
        raise SessionError(_error_text(response))
    try:
        data = response.json()
        value = str(data["value"])
    except (ValueError, KeyError, TypeError) as exc:
        raise SessionError("OpenAI sent a reply without a client secret.") from exc
    logger.info("client secret", extra={"kind": "call.session", "ok": True})
    return {
        "value": value,
        "expires_at": data.get("expires_at"),
        "model": config["model"],
        "transcribe_model": config["audio"]["input"]["transcription"]["model"],
        "voice": config["audio"]["output"]["voice"],
        "tools": [t["name"] for t in config["tools"]],
    }


def parse_arguments(raw: Any) -> dict:
    """Tool arguments arrive as a JSON string from the data channel."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
