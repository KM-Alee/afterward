"""Call-room routes. Audio stays on our server. A browser call is not a phone call."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from app.call.acceptance import CallRoom, OfferedTerms, Turn, hash_terms
from app.call.live import agent_turn, speak_aloud
from app.call.realtime_session import OpenAIRealtimeSession, realtime_allowed
from app.call.tools import bind_room, build_call_agent
from app.contracts import CallEvent, CallEventKind, CallTransport
from app.fakes import FakeCallSession
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


async def start_room(request_or_ws, room: CallRoom, token: str) -> None:
    """Start the call on the real realtime session when allowed, else a labelled rehearsal."""
    if room.session.started and not room.session.stopped:
        return
    settings = getattr(request_or_ws.app.state, "settings", None)
    if realtime_allowed(settings) and not isinstance(room.session, OpenAIRealtimeSession):
        session = OpenAIRealtimeSession(settings, room=room)
        _hook_events(request_or_ws, room, token, session)
        room.session = session
        room.mode = "realtime"
        room.mode_note = ""
    elif isinstance(room.session, OpenAIRealtimeSession):
        room.session.attach_room(room)
    else:
        room.mode = "rehearsal"
    bind_room(room)
    try:
        await room.start()
    except Exception:
        logger.info("realtime start", extra={"kind": "call.realtime", "ok": False})
        room.session = FakeCallSession()
        room.mode = "rehearsal"
        room.mode_note = "The live model could not be reached."
        await room.start()


def _hook_events(request_or_ws, room: CallRoom, token: str, session: OpenAIRealtimeSession) -> None:
    """Publish call events and ask the family once when the model records an offer."""
    surface = get_surface(request_or_ws)
    case_id = surface.call_tokens[token]
    app = request_or_ws.app

    def _on_event(event: CallEvent) -> None:
        if event.kind is CallEventKind.terms_offered:
            payload = event.payload
            try:
                offered = OfferedTerms(
                    int(str(payload.get("months"))),
                    str(payload.get("monthly_price")).lstrip("$"),
                    str(payload.get("number_kept")),
                    str(payload.get("voicemail_preserved")),
                )
            except (TypeError, ValueError):
                return
            if room.terms is None or room.terms_hash != hash_terms(offered):
                asyncio.ensure_future(room.report_offered_terms(offered))
            if ask_family_once(room):
                asyncio.ensure_future(_tell_owner(app, surface, case_id, room))
        surface.live.publish(
            case_id, "call.turn", {"via": "realtime", "summary": "Call event"}, actor="call"
        )

    session.on_event = _on_event


async def _tell_owner(app, surface, case_id, room: CallRoom) -> None:
    from app.runtime import notify_owner
    from app.web.router import _token_for

    if room.terms is None:
        return
    settings = getattr(app.state, "settings", None)
    base = getattr(settings, "public_base_url", "") if settings is not None else ""
    family = _token_for(surface.family_tokens, case_id)
    try:
        await notify_owner(
            app,
            f"On the call, Northline offered {room.terms.months} months at "
            f"${room.terms.price} a month. Nothing is accepted unless you approve it: "
            f"{base}/family/{family}",
        )
    except Exception:
        logger.info("owner notice", extra={"kind": "channel.send", "ok": False})


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
    await start_room(request, room, token)
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
    await start_room(request, room, token)
    await room.handle_typed_turn(text)
    surface = get_surface(request)
    case_id = surface.call_tokens[token]
    asked = ask_family_once(room)
    settings = getattr(request.app.state, "settings", None)
    live = room.mode == "realtime"
    # The live session answers this turn itself; the one-shot reply path is for rehearsal.
    via = "realtime" if live else await agent_turn(settings, room, text)
    if not live and room.turns and room.turns[-1].who == "agent":
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
        await _tell_owner(request.app, surface, case_id, room)
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
    """The live call: mic audio in, agent audio and transcript out, typed lines both ways.

    Binary frames are PCM16 mono 24 kHz. Text frames are JSON: `{"type": "line", "text"}`
    sends what the representative says, `{"type": "continue"}` asks for the approved sentence
    (re-checked against the terms first). Plain text is treated as a line. Server frames:
    `call.ready`, `turn` (one transcript line), `state` (offer and approval), `event`, `ended`.
    A browser call is not a phone call.
    """
    await websocket.accept()
    surface = get_surface(websocket)
    room = surface.calls.get(token)
    if room is None or token not in surface.call_tokens:
        await websocket.send_json({"kind": "missing"})
        await websocket.close(code=1008)
        return
    if room.status == "none":
        await websocket.send_json({"kind": "not_started"})
        await websocket.close(code=1008)
        return
    await start_room(websocket, room, token)
    await websocket.send_json(
        {
            "kind": "call.ready",
            "transport": "browser",
            "mode": room.mode,
            "label": room.mode_label,
            "note": room.mode_note,
            "phone": False,
            "turns": len(room.turns),
        }
    )
    case_id = surface.call_tokens[token]
    sender = asyncio.create_task(_send_out(websocket, room, token))
    try:
        while True:
            incoming = await websocket.receive()
            if incoming.get("type") == "websocket.disconnect":
                break
            payload = incoming.get("bytes")
            if payload:
                if room.session.stopped:
                    continue
                await room.on_representative_speech()
                await room.session.relay_audio_in(payload)
                continue
            text = incoming.get("text")
            if text:
                await _socket_message(websocket, room, token, case_id, text)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.info(
            "call socket", extra={"kind": "call.ws", "ok": False, "error": type(exc).__name__}
        )
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"kind": "error", "text": "The call connection had a problem. Reconnecting."}
            )
    finally:
        sender.cancel()


async def _socket_message(websocket: WebSocket, room: CallRoom, token: str, case_id, raw: str):
    try:
        message = json.loads(raw)
    except ValueError:
        message = {"type": "line", "text": raw}
    if not isinstance(message, dict):
        return
    kind = message.get("type")
    if kind == "line":
        text = " ".join(str(message.get("text") or "").split())[:500]
        if not text:
            return
        if room.session.stopped:
            await start_room(websocket, room, token)
        await room.handle_typed_turn(text)
        app = websocket.app
        surface = get_surface(websocket)
        if room.mode != "realtime":
            settings = getattr(app.state, "settings", None)
            await agent_turn(settings, room, text)
        if ask_family_once(room) and room.terms is not None:
            await _tell_owner(app, surface, case_id, room)
        surface.live.publish(
            case_id, "call.turn", {"via": "typed", "summary": "Call turn recorded"}, actor="call"
        )
    elif kind == "continue":
        await room.try_play_acceptance()
    elif kind == "interrupt":
        interrupt = getattr(room.session, "interrupt", None)
        if interrupt is not None and not room.session.stopped:
            await interrupt()


def _turn_frame(turn: Turn) -> dict:
    return {"kind": "turn", "who": turn.who, "text": turn.text, "via": turn.via, "type": turn.kind}


def _state_frame(room: CallRoom) -> dict:
    terms = room.terms
    return {
        "kind": "state",
        "approval": room.approval_status,
        "terms": (
            {"months": terms.months, "price": str(terms.price)} if terms is not None else None
        ),
        "can_continue": room.approval_status == "approved" and not room.acceptance_played,
    }


async def _send_out(websocket: WebSocket, room: CallRoom, token: str) -> None:
    """Stream new transcript lines, offer/approval changes, events, counters and agent audio.

    If the model connection drops on its own, reconnect the room instead of going silent.
    """
    sent_events = len(room.session.events())
    sent_turns = len(room.turns)
    sent_live = len(getattr(room.session, "live", []))
    last_state: dict | None = None
    last_stats = 0.0
    try:
        while True:
            if room.session.stopped and getattr(room.session, "lost", False):
                await websocket.send_json(
                    {"kind": "error", "text": "The model connection dropped. Reconnecting…"}
                )
                await start_room(websocket, room, token)
                sent_events = len(room.session.events())
                sent_live = len(getattr(room.session, "live", []))
                await websocket.send_json(
                    {
                        "kind": "call.ready",
                        "mode": room.mode,
                        "label": room.mode_label,
                        "note": room.mode_note,
                        "transport": "browser",
                        "phone": False,
                    }
                )
            live = getattr(room.session, "live", None)
            if isinstance(live, list):
                for frame in live[sent_live:]:
                    await websocket.send_json(frame)
                sent_live = len(live)
            now = asyncio.get_running_loop().time()
            stats = getattr(room.session, "stats", None)
            if isinstance(stats, dict) and now - last_stats >= 2:
                await websocket.send_json({"kind": "stats", **stats})
                last_stats = now
            for turn in room.turns[sent_turns:]:
                await websocket.send_json(_turn_frame(turn))
            sent_turns = len(room.turns)
            state = _state_frame(room)
            if state != last_state:
                await websocket.send_json(state)
                last_state = state
            events = room.session.events()
            for event in events[sent_events:]:
                if event.kind is CallEventKind.transcript:
                    continue  # the room's turns carry the transcript
                await websocket.send_json(
                    {"kind": "event", "event": event.kind.value, "payload": dict(event.payload)}
                )
            sent_events = len(events)
            heard = False
            if not room.session.stopped:
                async for chunk in room.session.relay_audio_out():
                    heard = True
                    await websocket.send_bytes(chunk)
            if room.session.stopped:
                await websocket.send_json({"kind": "ended"})
                return
            if not heard:
                await asyncio.sleep(0.1)
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        return


def agent_for_tests():
    """Build the realtime agent once a caller asks. Importing this module does not connect."""
    return build_call_agent()
