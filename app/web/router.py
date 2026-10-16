"""Desk, family, provider, proofs and the landing page."""

from __future__ import annotations

import hmac
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
    SurfaceState,
    build_surface,
    case_time_label,
)

router = APIRouter()


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
    surface.live.publish(
        case_id,
        "clock.advanced",
        {"days": days, "summary": f"Demo clock moved {days} days"},
        actor="desk",
    )
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
    report = run_proof_panel()
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
    board = surface.cases[case_id]
    return render(
        request,
        "family.html",
        _page(
            request,
            "family",
            board=board,
            token=token,
            options=FAMILY_OPTIONS,
            fit_always=True,
            reveal=True,
        ),
    )


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
            notice="" if sent != "1" else "Recorded in the demo mailbox as sent.",
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
    surface.live.publish(
        case_id,
        "provider.reply",
        {"provider": provider_id, "status": "sent", "summary": f"{profile['name']} reply recorded"},
        actor="provider",
    )
    return RedirectResponse(f"/provider/{token}?sent=1", status_code=303)


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
