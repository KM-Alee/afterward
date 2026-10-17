"""Call-room routes. Audio stays on our server. A browser call is not a phone call."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from app.call.acceptance import CallRoom, Turn
from app.call.live import agent_turn, speak_aloud
from app.call.tools import bind_room, build_call_agent
from app.contracts import CallTransport
from app.web.render import render
from app.web.router import _page, get_surface

router = APIRouter()
logger = logging.getLogger(__name__)

SUGGESTED_LINES = (
    ("greet", "Say hello", "Hello, you're through to Northline bereavement."),
    (
        "offer",
        "Offer $30 a month",
        "We can keep the number and voicemail for 12 months at $30 a month.",
    ),
    ("change", "Change it to $35", "Sorry, that offer is now 12 months at $35 a month."),
    ("confirm", "Promise it in writing", "We will confirm the transfer in writing."),
)


def ask_family_once(room: CallRoom) -> bool:
    """Code, not the model, asks Sara about each new offer exactly once."""
    if room.terms is None or room.approval_status == "approved":
        return False
    if getattr(room, "asked_hash", None) == room.terms_hash:
        return False
    room.asked_hash = room.terms_hash  # type: ignore[attr-defined]
    if room.approval_status == "none":
        room.approval_status = "pending"
    room.turns.append(
        Turn(
            who="system",
            text=(
                f"Sara was asked on the family card about {room.terms.months} months at "
                f"${room.terms.price} a month. Nothing was accepted."
            ),
            kind="decision",
        )
    )
    return True


def _room_for(request: Request, token: str) -> CallRoom | None:
    surface = get_surface(request)
    if token not in surface.call_tokens:
        return None
    return surface.calls.get(token)


@router.get("/call/{token}")
def call_room(request: Request, token: str):
    room = _room_for(request, token)
    if room is None:
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=404, message="That call link is not valid."),
            status_code=404,
        )
    surface = get_surface(request)
    case_id = surface.call_tokens[token]
    return render(
        request,
        "call.html",
        _page(
            request,
            "call",
            room=room,
            token=token,
            board=surface.cases[case_id],
            lines=SUGGESTED_LINES,
            phone_calls_enabled=surface.phone_calls_enabled,
            reveal=True,
        ),
    )


@router.post("/call/{token}/join")
async def join_call(request: Request, token: str):
    room = _room_for(request, token)
    if room is None or room.status == "none":
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=404, message="There is no call to join."),
            status_code=404,
        )
    bind_room(room)
    await room.start()
    return RedirectResponse(f"/call/{token}", status_code=303)


@router.post("/api/calls/{token}/turn")
async def typed_turn(request: Request, token: str):
    room = _room_for(request, token)
    if room is None or room.status == "none":
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=404, message="There is no call for that link."),
            status_code=404,
        )
    form = await request.form()
    text = str(form.get("text") or "").strip() or str(form.get("line") or "").strip()
    if not text:
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=422, message="Type a turn before sending."),
            status_code=422,
        )
    bind_room(room)
    await room.handle_typed_turn(text)
    surface = get_surface(request)
    case_id = surface.call_tokens[token]
    asked = ask_family_once(room)
    settings = getattr(request.app.state, "settings", None)
    via = await agent_turn(settings, room, text)
    if room.turns and room.turns[-1].who == "agent":
        try:
            room.spoken_b64 = await asyncio.wait_for(speak_aloud(settings, room.turns[-1].text), 8)
        except Exception:
            logger.info("call speech", extra={"kind": "call.tts", "ok": False})
            room.spoken_b64 = None
    surface.live.publish(
        case_id,
        "call.turn",
        {"via": via, "summary": "Call turn recorded"},
        actor="call",
    )
    if asked and room.terms is not None:
        from app.runtime import notify_owner
        from app.web.router import _token_for

        base = getattr(settings, "public_base_url", "") if settings is not None else ""
        family = _token_for(surface.family_tokens, case_id)
        try:
            await notify_owner(
                request.app,
                f"On the call, Northline offered {room.terms.months} months at "
                f"${room.terms.price} a month. Nothing is accepted unless you approve it: "
                f"{base}/family/{family}",
            )
        except Exception:
            logger.info("owner notice", extra={"kind": "channel.send", "ok": False})
    return RedirectResponse(f"/call/{token}", status_code=303)


@router.post("/api/calls/{token}/continue")
async def continue_acceptance(request: Request, token: str):
    """Play the server sentence only if the approved terms hash still matches."""
    room = _room_for(request, token)
    if room is None:
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=404, message="That call link is not valid."),
            status_code=404,
        )
    await room.try_play_acceptance()
    if room.acceptance_played and room.sentence:
        room.spoken_b64 = await speak_aloud(
            getattr(request.app.state, "settings", None), room.sentence
        )
    return RedirectResponse(f"/call/{token}", status_code=303)


@router.post("/api/calls/{token}/dial")
async def dial(request: Request, token: str):
    """Phone transport stays off unless the operator enabled it. This does not place a call."""
    surface = get_surface(request)
    if token not in surface.call_tokens:
        return render(
            request,
            "error.html",
            _page(request, "call", status_code=404, message="That call link is not valid."),
            status_code=404,
        )
    if not surface.phone_calls_enabled:
        return render(
            request,
            "error.html",
            _page(
                request,
                "call",
                status_code=403,
                message="Phone calls are off. This room is a browser call, not a phone call.",
            ),
            status_code=403,
        )
    room = surface.calls[token]
    await room.session.start(CallTransport.phone)
    return RedirectResponse(f"/call/{token}", status_code=303)


@router.websocket("/ws/calls/{token}")
async def call_socket(websocket: WebSocket, token: str):
    """Relay browser audio through the call session. This does not open an OpenAI socket."""
    await websocket.accept()
    surface = get_surface(websocket)
    room = surface.calls.get(token)
    if room is None or token not in surface.call_tokens:
        await websocket.send_json({"kind": "missing"})
        await websocket.close(code=1008)
        return
    bind_room(room)
    await room.start()
    await websocket.send_json({"kind": "call.ready", "transport": "browser"})
    try:
        while True:
            incoming = await websocket.receive()
            if incoming.get("type") == "websocket.disconnect":
                break
            payload = incoming.get("bytes")
            if payload:
                await room.on_representative_speech()
                await room.session.relay_audio_in(payload)
                continue
            text = incoming.get("text")
            if text:
                await room.handle_typed_turn(text)
                await websocket.send_json({"kind": "turn", "via": "typed"})
    except WebSocketDisconnect:
        return


def agent_for_tests():
    """Build the realtime agent once a caller asks. Importing this module does not connect."""
    return build_call_agent()
