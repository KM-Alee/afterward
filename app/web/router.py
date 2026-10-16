"""Desk, family, provider, proofs and the landing page."""

from __future__ import annotations

import hmac
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from app.contracts import SendRequest
from app.web.proofs import PROOF_CASES, run_proof_panel
from app.web.render import render
from app.web.state import (
    FOOTER_REF,
    PROVIDERS,
    VARIANTS,
    CaseBoard,
    SurfaceState,
    TimelineEvent,
    build_surface,
    case_time_label,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _send_fitlife_followup(surface: SurfaceState) -> None:
    """One follow-up after the +14 day jump. FitLife's window is 10 business days."""
    already = [
        record
        for record in surface.mailbox.sent
        if "FL-5531" in record.text or "following up" in record.text.casefold()
    ]
    if already:
        return
    profile = PROVIDERS["fitlife"]
    text = (
        "Following up on membership FL-5531. "
        "Please confirm the cancellation in writing.\n\n"
        "Ref AW-1042-FL1"
    )
    await surface.mailbox.send(
        SendRequest(
            mailbox="family@demo.example",
            to_addrs=[profile["recipient"]],
            subject=profile["subject"],
            text=text,
            footer_ref="AW-1042-FL1",
            from_name="Afterward",
        )
    )


BOUNDARY_NOTE = (
    "Confidential compute protects our compute and storage. It does not extend to the "
    "AI provider, the chat platforms or the recipients, and we say so."
)

FAMILY_OPTIONS = (
    ("ask", "Ask them to fix it", "Keep the voicemail, no contract"),
    ("call", "Call them for me", "I'll check with you before agreeing to anything"),
    ("accept", "Accept anyway", "The voicemail is reset and the 24-month plan stays"),
)


def get_surface(request: Request) -> SurfaceState:
    surface = getattr(request.app.state, "surface", None)
    if surface is None:
        surface = build_surface("")
        request.app.state.surface = surface
    return surface


def signed_in(request: Request) -> bool:
    token = request.cookies.get("aw_desk", "")
    return bool(token) and token in get_surface(request).sessions


def passcode_matches(supplied: str, expected: str) -> bool:
    if not supplied or not expected:
        return False
    left = supplied.encode()
    right = expected.encode()
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _token_for(mapping: dict[str, UUID], case_id: UUID) -> str:
    for token, owner in mapping.items():
        if owner == case_id:
            return token
    return ""


def _nav(request: Request, current: str, *, reveal: bool = False) -> list[dict[str, str]]:
    surface = get_surface(request)
    demo = surface.demo_case_id
    items = [
        {"id": "index", "href": "/", "label": "Start", "icon": "horizon"},
        {"id": "desk", "href": f"/desk/{demo}", "label": "Case desk", "icon": "desk"},
        {
            "id": "family",
            "href": f"/family/{_token_for(surface.family_tokens, demo)}",
            "label": "Family",
            "icon": "users",
        },
        {
            "id": "call",
            "href": f"/call/{_token_for(surface.call_tokens, demo)}",
            "label": "Call room",
            "icon": "phone",
        },
        {
            "id": "provider",
            "href": f"/provider/{_token_for(surface.provider_tokens, demo)}",
            "label": "Provider console",
            "icon": "building",
        },
        {"id": "proofs", "href": "/proofs", "label": "Proofs", "icon": "flask"},
    ]
    if not signed_in(request) and not reveal:
        items = [item for item in items if item["id"] == "index"]
    for item in items:
        item["current"] = "true" if item["id"] == current else ""
    return items


def _page(request: Request, current: str, **extra: object) -> dict[str, object]:
    reveal = bool(extra.pop("reveal", False))
    return {
        "nav": _nav(request, current, reveal=reveal),
        "signed_in": signed_in(request),
        "boundary_note": BOUNDARY_NOTE,
        "page": current,
        **extra,
    }


@router.get("/")
def landing(request: Request):
    surface = get_surface(request)
    return render(
        request,
        "index.html",
        _page(
            request,
            "index",
            error="",
            doors=_doors(surface) if signed_in(request) else [],
        ),
    )


@router.post("/access")
async def access(request: Request):
    form = await request.form()
    supplied = str(form.get("passcode") or "")
    surface = get_surface(request)
    if not passcode_matches(supplied, surface.demo_passcode):
        message = (
            "Enter the demo passcode. It is in the submission PDF."
            if not supplied
            else "That passcode did not work. Check the submission PDF."
        )
        return render(
            request,
            "index.html",
            _page(request, "index", error=message, doors=[]),
            status_code=401,
        )
    session = secrets.token_urlsafe(32)
    surface.sessions.add(session)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("aw_desk", session, httponly=True, samesite="lax")
    return response


def _doors(surface: SurfaceState) -> list[dict[str, str]]:
    demo = surface.demo_case_id
    return [
        {
            "href": f"/desk/{demo}",
            "icon": "desk",
            "title": "Case desk",
            "detail": "The whole case at a glance",
        },
        {
            "href": f"/family/{_token_for(surface.family_tokens, demo)}",
            "icon": "users",
            "title": "Family",
            "detail": "Sara and Amina's cards",
        },
        {
            "href": f"/call/{_token_for(surface.call_tokens, demo)}",
            "icon": "phone",
            "title": "Call room",
            "detail": "Browser call, not a phone call",
        },
        {
            "href": f"/provider/{_token_for(surface.provider_tokens, demo)}",
            "icon": "building",
            "title": "Provider console",
            "detail": "Reply as an organisation",
        },
        {"href": "/proofs", "icon": "flask", "title": "Proofs", "detail": "The 14 cases"},
    ]


def _require_desk(request: Request):
    if signed_in(request):
        return None
    return render(
        request,
        "index.html",
        _page(
            request,
            "index",
            error="Enter the demo passcode to open this page.",
            doors=[],
        ),
        status_code=401,
    )


@router.get("/desk/{case_id}")
def desk(request: Request, case_id: UUID):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    board = surface.cases.get(case_id)
    if board is None:
        return render(
            request,
            "error.html",
            _page(request, "desk", status_code=404, message="That case link is not valid."),
            status_code=404,
        )
    call_token = _token_for(surface.call_tokens, case_id)
    room = surface.calls.get(call_token)
    return render(
        request,
        "desk.html",
        _page(
            request,
            "desk",
            board=board,
            case_time=case_time_label(surface, board),
            call_token=call_token,
            room=room,
        ),
    )


@router.post("/api/cases/{case_id}/clock")
async def advance_clock(request: Request, case_id: UUID):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    board = surface.cases.get(case_id)
    if board is None:
        return render(
            request,
            "error.html",
            _page(request, "desk", status_code=404, message="That case link is not valid."),
            status_code=404,
        )
    form = await request.form()
    try:
        days = int(str(form.get("advance_days") or ""))
    except ValueError:
        days = 0
    if days not in {14, 35}:
        return render(
            request,
            "error.html",
            _page(
                request,
                "desk",
                status_code=422,
                message="The demo clock only moves 14 or 35 days.",
            ),
            status_code=422,
        )
    if not board.is_demo:
        return render(
            request,
            "error.html",
            _page(request, "desk", status_code=403, message="The case clock is demo only."),
            status_code=403,
        )
    board.clock_case.clock_offset_s += days * 86400
    if days == 14:
        await _send_fitlife_followup(surface)
        await _relay_fitlife_followup(request, surface, board)
    surface.live.publish(
        case_id,
        "clock.advanced",
        {"days": days, "summary": f"Demo clock moved {days} days"},
        actor="desk",
    )
    return RedirectResponse(f"/desk/{case_id}", status_code=303)


@router.post("/api/cases/{case_id}/reset")
def reset_demo(request: Request, case_id: UUID):
    """Start the Malik story again: board, call room, demo mailbox and chat state."""
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    if case_id != surface.demo_case_id:
        return render(
            request,
            "error.html",
            _page(request, "desk", status_code=403, message="Only the demo case can be reset."),
            status_code=403,
        )
    from app.call.acceptance import CallRoom
    from app.fakes import FakeCallSession, FakeMailbox
    from app.story import mail_ready

    fresh = build_surface("")
    board = fresh.cases[case_id]
    if mail_ready(getattr(request.app.state, "settings", None)):
        board.monitoring = "ok"
    surface.cases[case_id] = board
    surface.mailbox = FakeMailbox()
    for token, owner in surface.call_tokens.items():
        if owner == case_id:
            surface.calls[token] = CallRoom(session=FakeCallSession(), status="ready")
    request.app.state.conversation = None
    surface.live.publish(case_id, "demo.reset", {"summary": "Demo reset"}, actor="desk")
    return RedirectResponse(f"/desk/{case_id}", status_code=303)


@router.get("/proofs")
def proofs(request: Request):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    report = surface.proof_history[-1] if surface.proof_history else None
    return render(
        request,
        "proofs.html",
        _page(request, "proofs", report=report, proof_cases=PROOF_CASES),
    )


@router.post("/api/proofs/run")
def run_proofs(request: Request):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    report = run_proof_panel(live=bool(getattr(request.app.state, "run_proofs_live", False)))
    surface.proof_history.append(report)
    surface.live.publish(
        surface.demo_case_id,
        "proofs.finished",
        {"status": str(report.get("status", "not_run")), "summary": "Proof panel updated"},
        actor="desk",
    )
    return render(
        request,
        "proofs.html",
        _page(request, "proofs", report=report, proof_cases=PROOF_CASES),
    )


@router.get("/family/{token}")
def family(request: Request, token: str):
    surface = get_surface(request)
    case_id = surface.family_tokens.get(token)
    if case_id is None:
        return render(
            request,
            "error.html",
            _page(request, "family", status_code=404, message="That family link is not valid."),
            status_code=404,
        )
    return _family_page(request, token, case_id)


def _family_page(
    request: Request, token: str, case_id: UUID, *, error: str = "", status_code: int = 200
):
    surface = get_surface(request)
    board = surface.cases[case_id]
    room = surface.calls.get(_token_for(surface.call_tokens, case_id))
    offer = room if room is not None and room.terms is not None else None
    return render(
        request,
        "family.html",
        _page(
            request,
            "family",
            board=board,
            token=token,
            options=FAMILY_OPTIONS,
            offer=offer,
            offer_error=error,
            fit_always=True,
            reveal=True,
        ),
        status_code=status_code,
    )


@router.post("/family/{token}/call")
async def family_call_decision(request: Request, token: str):
    """Sara approves or declines the offer she saw. A changed offer refuses the old approval."""
    surface = get_surface(request)
    case_id = surface.family_tokens.get(token)
    if case_id is None:
        return render(
            request,
            "error.html",
            _page(request, "family", status_code=404, message="That family link is not valid."),
            status_code=404,
        )
    room = surface.calls.get(_token_for(surface.call_tokens, case_id))
    form = await request.form()
    choice = str(form.get("choice") or "")
    seen_hash = str(form.get("terms_hash") or "")
    if room is None or room.terms is None or choice not in {"approve", "decline"}:
        return _family_page(
            request, token, case_id, error="There is no offer to decide.", status_code=422
        )
    from app.call.acceptance import Turn

    if choice == "decline":
        room.approval_status = "declined"
        room.turns.append(
            Turn("system", "Sara declined the offer. Nothing was accepted.", "", "decision")
        )
        summary = "Sara declined the call offer"
    else:
        try:
            room.approve(seen_hash)
        except ValueError:
            return _family_page(
                request,
                token,
                case_id,
                error="Northline changed the offer before you tapped. Look at the new offer.",
                status_code=409,
            )
        await room.queue_acceptance()
        room.turns.append(
            Turn(
                "system",
                "Sara approved this exact offer. The agent says the fixed sentence only after "
                "the terms are checked again.",
                "",
                "decision",
            )
        )
        summary = "Sara approved the call offer"
    surface.live.publish(case_id, "call.decision", {"summary": summary}, actor="family")
    return RedirectResponse(f"/family/{token}", status_code=303)


@router.post("/family/{token}/decision")
async def family_decision(request: Request, token: str):
    surface = get_surface(request)
    case_id = surface.family_tokens.get(token)
    if case_id is None:
        return render(
            request,
            "error.html",
            _page(request, "family", status_code=404, message="That family link is not valid."),
            status_code=404,
        )
    form = await request.form()
    choice = str(form.get("choice") or "")
    allowed = {item[0] for item in FAMILY_OPTIONS}
    if choice not in allowed:
        return render(
            request,
            "error.html",
            _page(request, "family", status_code=422, message="That choice is not on the card."),
            status_code=422,
        )
    board = surface.cases[case_id]
    board.family_choice = choice
    surface.live.publish(
        case_id,
        "family.decided",
        {"choice": choice, "summary": "Sara chose on the family card"},
        actor="family",
    )
    return RedirectResponse(f"/family/{token}", status_code=303)


@router.get("/provider/{token}")
def provider(request: Request, token: str, sent: str = ""):
    surface = get_surface(request)
    case_id = surface.provider_tokens.get(token)
    if case_id is None:
        return render(
            request,
            "error.html",
            _page(request, "provider", status_code=404, message="That provider link is not valid."),
            status_code=404,
        )
    board = surface.cases[case_id]
    return render(
        request,
        "provider.html",
        _page(
            request,
            "provider",
            board=board,
            token=token,
            providers=PROVIDERS,
            variants=VARIANTS,
            notice=(
                "Sent through the connected Gmail mailbox."
                if sent == "live"
                else ("" if sent != "1" else "Recorded in the demo mailbox as sent.")
            ),
            error="",
            reveal=True,
        ),
    )


@router.post("/api/provider/send")
async def provider_send(request: Request):
    surface = get_surface(request)
    form = await request.form()
    token = str(form.get("token") or "")
    provider_id = str(form.get("provider") or "")
    variant = str(form.get("variant") or "")
    text = str(form.get("text") or "").strip()
    case_id = surface.provider_tokens.get(token)
    if case_id is None:
        return render(
            request,
            "error.html",
            _page(request, "provider", status_code=404, message="That provider link is not valid."),
            status_code=404,
        )
    board = surface.cases[case_id]
    profile = PROVIDERS.get(provider_id)
    if profile is None:
        return render(
            request,
            "provider.html",
            _page(
                request,
                "provider",
                board=board,
                token=token,
                providers=PROVIDERS,
                variants=VARIANTS,
                notice="",
                error="Choose a provider.",
                reveal=True,
            ),
            status_code=422,
        )
    if not text and variant in VARIANTS and VARIANTS[variant]["provider"] == provider_id:
        text = VARIANTS[variant]["text"]
    if not text:
        return render(
            request,
            "provider.html",
            _page(
                request,
                "provider",
                board=board,
                token=token,
                providers=PROVIDERS,
                variants=VARIANTS,
                notice="",
                error="Write a reply before sending.",
                reveal=True,
            ),
            status_code=422,
        )
    thread = board.threads.get(provider_id)
    subject = thread.subject if thread else profile["subject"]
    body = f"{text}\n\n{FOOTER_REF}"
    live = await _relay_provider_mail(request, subject, body, profile["name"])
    await surface.mailbox.send(
        SendRequest(
            mailbox="providers@demo.example",
            to_addrs=["family@demo.example"],
            subject=subject,
            text=body,
            thread_id=f"thread-{provider_id}",
            footer_ref=FOOTER_REF,
            from_name=profile["name"],
        )
    )
    if thread is None:
        from app.web.state import ProviderThread

        thread = ProviderThread(provider_id, subject, "")
        board.threads[provider_id] = thread
    thread.replies.append({"text": text, "status": "sent"})
    if provider_id == "northline":
        await _apply_northline_outcome(request, surface, board, text)
    surface.live.publish(
        case_id,
        "provider.reply",
        {"provider": provider_id, "status": "sent", "summary": f"{profile['name']} reply recorded"},
        actor="provider",
    )
    sent_flag = "live" if live else "1"
    return RedirectResponse(f"/provider/{token}?sent={sent_flag}", status_code=303)


async def _relay_fitlife_followup(
    request: Request, surface: SurfaceState, board: CaseBoard
) -> None:
    """One Gmail follow-up for the +14 day jump. A second jump does not send another."""
    if any(event.text.startswith("FitLife follow-up sent") for event in board.events):
        return
    sent = await _relay_family_mail(
        request,
        PROVIDERS["fitlife"]["subject"],
        (
            "Following up on membership FL-5531. "
            "Please confirm the cancellation in writing.\n\n"
            "Ref AW-1042-FL1"
        ),
        "AW-1042-FL1",
    )
    if sent:
        board.events.append(
            TimelineEvent(
                "FitLife follow-up sent through the connected mailbox.",
                case_time_label(surface, board),
                "unverified",
                "system",
            )
        )
    found = await _find_sent(request, surface, "AW-1042-FL1", live=sent)
    board.delivery = "reconciled" if found else "uncertain"
    if found:
        board.events.append(
            TimelineEvent(
                "Checked the Sent folder before saying so: the FitLife follow-up is there.",
                case_time_label(surface, board),
                "unverified",
                "system",
            )
        )


async def _find_sent(request: Request, surface: SurfaceState, footer: str, *, live: bool) -> bool:
    """Look for the footer in Sent before saying a follow-up went."""
    if not live:
        return await surface.mailbox.search_sent("family@demo.example", footer) is not None
    settings = request.app.state.settings
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "family")
        return await mailbox.search_sent(settings.family_mailbox, footer) is not None
    except Exception:
        logger.info("sent search", extra={"kind": "mail.reconcile", "ok": False})
        return False


async def _relay_family_mail(request: Request, subject: str, body: str, footer_ref: str) -> bool:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not _mail_ready(settings):
        return False
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "family")
        await mailbox.send(
            SendRequest(
                mailbox=settings.family_mailbox,
                to_addrs=[settings.providers_mailbox],
                subject=subject,
                text=body,
                footer_ref=footer_ref,
                from_name="Afterward",
            )
        )
    except Exception:
        logger.info("family mail", extra={"kind": "mail.relay", "ok": False})
        return False
    return True


async def _apply_northline_outcome(
    request: Request, surface: SurfaceState, board: CaseBoard, text: str
) -> None:
    """Check the Northline reply with the engine and show that result on the desk."""
    ai = getattr(request.app.state, "reply_reader", None)
    settings = getattr(request.app.state, "settings", None)
    if ai is None:
        if settings is None or not settings.openai_api_key.get_secret_value():
            return
        from app.ai.client import AgentsSDKClient

        ai = AgentsSDKClient(settings)
    if board.outcome is None:
        return
    from app.story import read_northline_reply, show_northline_verdict

    try:
        verdict, commitments = await read_northline_reply(ai, text)
    except Exception:
        logger.info("outcome check", extra={"kind": "outcome.live", "ok": False})
        return
    show_northline_verdict(surface, board, text, verdict, commitments)
    if verdict.verdict != "resolved":
        from app.runtime import notify_owner

        family_link = _token_for(surface.family_tokens, board.id)
        base = getattr(settings, "public_base_url", "") if settings is not None else ""
        try:
            await notify_owner(
                request.app,
                "Northline replied, and I have not treated it as done. "
                f"{board.outcome.verdict_text} "
                f"Choose on the family card: {base}/family/{family_link}",
            )
        except Exception:
            logger.info("owner notice", extra={"kind": "channel.send", "ok": False})


def _mail_ready(settings: object) -> bool:
    from app.story import mail_ready

    return mail_ready(settings)


async def _relay_provider_mail(request: Request, subject: str, body: str, from_name: str) -> bool:
    """Send the provider reply through Gmail when a mailbox token is configured."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.family_mailbox or not settings.providers_mailbox:
        return False
    if not (
        settings.google_client_id.get_secret_value()
        and settings.google_refresh_token_providers.get_secret_value()
    ):
        return False
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "providers")
        await mailbox.send(
            SendRequest(
                mailbox=settings.providers_mailbox,
                to_addrs=[settings.family_mailbox],
                subject=subject,
                text=body,
                footer_ref=FOOTER_REF,
                from_name=from_name,
            )
        )
    except Exception:
        logger.info("provider mail", extra={"kind": "mail.relay", "ok": False})
        return False
    return True


@router.websocket("/ws/cases/{case_id}")
async def case_events(websocket: WebSocket, case_id: UUID):
    """Push published desk events. The socket does not carry document bodies."""
    await websocket.accept()
    if not signed_in(websocket):
        await websocket.send_json({"kind": "denied"})
        await websocket.close(code=1008)
        return
    surface = get_surface(websocket)
    surface.live.attach(asyncio_loop())
    if case_id not in surface.cases:
        await websocket.send_json({"kind": "missing"})
        await websocket.close(code=1008)
        return
    queue = surface.live.subscribe_queue(case_id)
    await websocket.send_json({"kind": "stream.ready", "case_id": str(case_id)})
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        return
    finally:
        surface.live.unsubscribe_queue(case_id, queue)


def asyncio_loop():
    import asyncio

    return asyncio.get_running_loop()
