"""One agent turn per representative turn. Realtime text when a key is set, else a fixed line.

The model only speaks. It has no tools here, so it cannot record or accept terms; code
reads the offer from the representative's words and the speech check screens the reply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.call.acceptance import CallRoom
from app.call.tools import CALL_INSTRUCTIONS

logger = logging.getLogger(__name__)

REALTIME_TIMEOUT_S = 15.0
FALLBACK_OFFER = (
    "Thank you. I've noted {months} months at ${price} a month. "
    "I can't accept terms myself, so I'm asking the family now."
)
FALLBACK_LINE = (
    "Thank you. I'm calling about moving line 4417 to Amina Malik, "
    "keeping the number and the voicemail, with no new contract."
)


def _context(room: CallRoom) -> str:
    lines = []
    for turn in room.turns[-10:]:
        if turn.who == "rep":
            lines.append(f"Northline: {turn.text}")
        elif turn.who == "agent":
            lines.append(f"You: {turn.text}")
    terms = (
        f"Offer on the table: {room.terms.months} months at ${room.terms.price} a month. "
        "It is not accepted."
        if room.terms is not None
        else "No offer yet."
    )
    introduced = any(turn.kind == "disclosure" for turn in room.turns)
    return (
        f"{CALL_INSTRUCTIONS}\n"
        + (
            "You have already said you are an AI assistant on a browser call. "
            "Do not repeat that introduction.\n"
            if introduced
            else ""
        )
        + "The approved request: move Northline line 4417 to Amina Malik, keep the number and the "
        "existing voicemail, no new contract. "
        f"{terms} Family approval status: {room.approval_status}.\n"
        "Reply as spoken words, at most two short sentences. Never agree to an offer; say the "
        "family decides.\nTranscript so far:\n" + "\n".join(lines)
    )


def fallback_reply(room: CallRoom) -> str:
    if room.terms is not None and room.approval_status in {"pending", "void", "none"}:
        return FALLBACK_OFFER.format(months=room.terms.months, price=room.terms.price)
    return FALLBACK_LINE


async def realtime_reply(settings: Any, room: CallRoom, rep_text: str) -> str | None:
    """Open one realtime socket, send the representative's words, read the text reply."""
    key = settings.openai_api_key.get_secret_value() if settings is not None else ""
    if not key:
        return None
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=key)

    async def _turn() -> str:
        async with client.realtime.connect(model=settings.realtime_model) as conn:
            await conn.session.update(
                session={
                    "type": "realtime",
                    "output_modalities": ["text"],
                    "instructions": _context(room),
                }
            )
            await conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": rep_text}],
                }
            )
            await conn.response.create()
            text = ""
            async for event in conn:
                if event.type in {"response.output_text.delta", "response.text.delta"}:
                    text += event.delta
                elif event.type == "response.done" or event.type == "error":
                    break
            return text.strip()

    try:
        reply = await asyncio.wait_for(_turn(), REALTIME_TIMEOUT_S)
    except Exception:
        logger.info("realtime turn", extra={"kind": "call.realtime", "ok": False})
        return None
    return reply or None


async def speak_aloud(settings: Any, text: str) -> str | None:
    """Turn one reply into browser audio. Returns opus bytes as base64, or nothing."""
    if settings is None or not text or not settings.openai_api_key.get_secret_value():
        return None
    import base64

    from app.ai.client import AgentsSDKClient

    try:
        parts: list[bytes] = []
        async for chunk in AgentsSDKClient(settings).speak_stream(text, audio_format="opus"):
            parts.append(chunk.audio)
    except Exception:
        logger.info("call speech", extra={"kind": "call.tts", "ok": False})
        return None
    if not parts:
        return None
    return base64.b64encode(b"".join(parts)).decode("ascii")


async def agent_turn(settings: Any, room: CallRoom, rep_text: str) -> str:
    """Speak one agent reply through the speech check. Returns how it was produced."""
    reply = await realtime_reply(settings, room, rep_text)
    via = "realtime" if reply else "scripted"
    text = reply or fallback_reply(room)
    tripped = await room.screen_model_speech(text)
    if not tripped and room.turns:
        room.turns[-1].via = via
    return via
