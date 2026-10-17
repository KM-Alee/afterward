"""The showcase page: run the Malik story one real step at a time, behind the desk passcode."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.demo.showcase import (
    STEPS,
    ShowcaseEnv,
    ShowcaseError,
    StepResult,
    progress,
    reset_showcase,
    run_next,
    showcase_case,
)
from app.web.render import render
from app.web.router import _error, _page, _require_desk, _token_for, get_surface

router = APIRouter()
logger = logging.getLogger(__name__)

_LOCK_KEY = "showcase_lock"
_ENV_KEY = "showcase_env"


def _env(request: Request) -> ShowcaseEnv:
    env = getattr(request.app.state, _ENV_KEY, None)
    if env is None:
        env = ShowcaseEnv()
        setattr(request.app.state, _ENV_KEY, env)
    return env


def _lock(request: Request) -> asyncio.Lock:
    lock = getattr(request.app.state, _LOCK_KEY, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(request.app.state, _LOCK_KEY, lock)
    return lock


def _links(request: Request, kinds: list[str]) -> list[dict[str, str]]:
    """Pages where a step's effect is visible. Tokens come from the surface, not the step."""
    surface = get_surface(request)
    demo: UUID = surface.demo_case_id
    family = _token_for(surface.family_tokens, demo)
    table = {
        "desk": ("Case desk", f"/desk/{demo}"),
        "family": ("Family page", f"/family/{family}"),
        "onboarding": ("Finding accounts", f"/family/{family}/onboarding"),
        "call": ("Call room", f"/call/{_token_for(surface.call_tokens, demo)}"),
        "provider": ("Provider console", f"/provider/{_token_for(surface.provider_tokens, demo)}"),
    }
    return [{"label": table[k][0], "href": table[k][1]} for k in kinds if k in table]


def _blank_overlay(request: Request) -> None:
    """Blank the in-memory demo story while the showcase runs, so only database rows show."""
    surface = get_surface(request)
    board = surface.cases.get(surface.demo_case_id)
    if board is not None:
        board.events = []
        board.outcome = None
        board.threads = {}


def _reset_surface(request: Request) -> None:
    """Fresh call room and board overlay, like the desk's own reset, so nothing stale is shown."""
    from app.call.acceptance import CallRoom
    from app.fakes import FakeCallSession
    from app.web.state import attach_call_rooms, build_surface

    surface = get_surface(request)
    fresh = build_surface("")
    surface.cases[surface.demo_case_id] = fresh.cases[surface.demo_case_id]
    _blank_overlay(request)
    for token, owner in surface.call_tokens.items():
        if owner == surface.demo_case_id:
            surface.calls[token] = CallRoom(session=FakeCallSession(), status="ready")
    attach_call_rooms(surface)


def _view(request: Request) -> dict[str, object]:
    surface = get_surface(request)
    factory = surface.session_factory
    done: dict[str, dict] = {}
    started = False
    if factory is not None:
        with factory() as session:  # type: ignore[operator]
            started = showcase_case(session) is not None
            done = {item["step_id"]: item for item in progress(session)}
    rows = []
    marked = False
    for step in STEPS:
        result = done.get(step.id)
        state = "done" if result else ("next" if started and not marked else "todo")
        marked = marked or state == "next"
        rows.append(
            {
                "id": step.id,
                "title": step.title,
                "blurb": step.blurb,
                "state": state,
                "result": result,
                "links": _links(request, list((result or {}).get("links") or [])),
            }
        )
    return {
        "steps": rows,
        "started": started,
        "finished": started and all(r["state"] == "done" for r in rows),
        "has_db": factory is not None,
        "chat": list(_env(request).chat)[-12:],
    }


@router.get("/showcase")
def showcase_page(request: Request, error: str = ""):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    view = _view(request)
    if view["started"]:
        _blank_overlay(request)
    return render(request, "showcase.html", _page(request, "showcase", error=error, **view))


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _done(request: Request, payload: dict, status: int = 200):
    if _wants_json(request):
        return JSONResponse(payload, status_code=status)
    if status >= 400:
        return RedirectResponse(f"/showcase?error={payload.get('error', '')}", status_code=303)
    return RedirectResponse("/showcase#progress", status_code=303)


@router.post("/api/showcase/next")
async def showcase_next(request: Request):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    factory = surface.session_factory
    if factory is None:
        return _error(request, "showcase", 503, "The showcase needs the database.")
    async with _lock(request):
        try:
            result: StepResult | None = await run_next(factory, _env(request))  # type: ignore[arg-type]
        except ShowcaseError as exc:
            return _done(request, {"ok": False, "error": str(exc)}, 409)
        except Exception:
            logger.info("showcase step", extra={"kind": "showcase.step", "ok": False})
            return _done(
                request, {"ok": False, "error": "That step failed. Reset and try again."}, 500
            )
    _blank_overlay(request)
    if result is not None:
        surface.live.publish(
            surface.demo_case_id,
            "showcase.step",
            {"summary": result.headline, "step": result.step_id},
            actor="showcase",
        )
    payload = {"ok": True, "finished": result is None}
    if result is not None:
        payload.update(step=result.step_id, headline=result.headline)
    return _done(request, payload)


@router.post("/api/showcase/reset")
async def showcase_reset(request: Request):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    factory = surface.session_factory
    if factory is None:
        return _error(request, "showcase", 503, "The showcase needs the database.")
    async with _lock(request):
        try:
            with factory() as session:  # type: ignore[operator]
                reset_showcase(session)
                session.commit()
        except PermissionError:
            return _error(request, "showcase", 403, "Only the demo case can be reset.")
        setattr(request.app.state, _ENV_KEY, ShowcaseEnv())
    _reset_surface(request)
    surface.live.publish(
        surface.demo_case_id, "demo.reset", {"summary": "Showcase reset"}, actor="showcase"
    )
    return _done(request, {"ok": True, "reset": True})
