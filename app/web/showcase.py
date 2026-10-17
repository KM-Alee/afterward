"""The showcase page: run the Malik story one real step at a time, behind the desk passcode."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.demo import showcase_data
from app.demo.showcase import (
    LIVE_LABEL,
    STEPS,
    LiveInputError,
    ShowcaseEnv,
    ShowcaseError,
    StepResult,
    live_dependency,
    live_intake,
    live_reply,
    progress,
    reset_showcase,
    run_next,
    run_to,
    save_tour_state,
    showcase_case,
    tour_state,
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


# --------------------------------------------------------------------------------------
# Guided tour
# --------------------------------------------------------------------------------------
_AI_KEY = "showcase_ai"
_MAX_TEXT = 1500


def _live_ai(request: Request):
    """The real model client when a key is configured (or one was injected); else None."""
    injected = getattr(request.app.state, _AI_KEY, None)
    if injected is not None:
        return injected
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.openai_api_key.get_secret_value():
        return None
    from app.ai.client import AgentsSDKClient

    client = AgentsSDKClient(settings, timeout_s=45, max_retries=1)
    setattr(request.app.state, _AI_KEY, client)
    return client


def _tour_links(request: Request) -> dict[str, str]:
    surface = get_surface(request)
    demo: UUID = surface.demo_case_id
    family = _token_for(surface.family_tokens, demo)
    return {
        "home": "/",
        "showcase": "/showcase",
        "desk": f"/desk/{demo}",
        "family": f"/family/{family}",
        "onboarding": f"/family/{family}/onboarding",
        "provider": f"/provider/{_token_for(surface.provider_tokens, demo)}",
        "call": f"/call/{_token_for(surface.call_tokens, demo)}",
        "proofs": "/proofs",
    }


def _step_payload(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "step": row["step_id"],
        "headline": row["headline"],
        "details": list(row.get("details") or [])[:6],
        "real": list(row.get("real") or [])[:3],
        "simulated": list(row.get("simulated") or [])[:2],
    }


@router.get("/api/showcase/tour")
def tour_config(request: Request):
    """The tour script with resolved page URLs, step progress and saved position."""
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    factory = surface.session_factory
    links = _tour_links(request)
    state = {"active": False, "index": 0, "live": {}}
    done: dict[str, dict] = {}
    started = False
    if factory is not None:
        with factory() as session:  # type: ignore[operator]
            state = tour_state(session)
            done = {item["step_id"]: item for item in progress(session)}
            started = showcase_case(session) is not None
    stops = [
        {
            **stop,
            "url": links.get(stop["page"], "/"),
            "autoplay": showcase_data.AUTOPLAY.get(stop["id"], {"say": stop["text"], "dwell": 8}),
        }
        for stop in showcase_data.TOUR
    ]
    return JSONResponse(
        {
            "stops": stops,
            "state": state,
            "done": {key: _step_payload(value) for key, value in done.items()},
            "model": LIVE_LABEL if _live_ai(request) is not None else "Recorded model output",
            "has_db": factory is not None,
            "started": started,
            "links": links,
        }
    )


@router.post("/api/showcase/tour/state")
async def tour_save(request: Request):
    denied = _require_desk(request)
    if denied is not None:
        return denied
    factory = get_surface(request).session_factory
    if factory is None:
        return JSONResponse({"ok": False, "error": "The showcase needs the database."}, 503)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    patch = {k: body[k] for k in ("active", "index") if k in body}
    if isinstance(body.get("live"), dict):
        patch["live"] = body["live"]
    try:
        with factory() as session:  # type: ignore[operator]
            state = save_tour_state(session, patch)
            session.commit()
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Bad tour state."}, 422)
    return JSONResponse({"ok": True, "state": state})


async def _text_of(request: Request) -> str | None:
    try:
        body = await request.json()
    except ValueError:
        return None
    text = body.get("text") if isinstance(body, dict) else None
    return text.strip()[:_MAX_TEXT] if isinstance(text, str) and text.strip() else None


async def _live(request: Request, name: str):
    """Shared wrapper: desk auth, input check, one showcase lock, model-or-recorded run."""
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    factory = surface.session_factory
    if factory is None:
        return JSONResponse({"ok": False, "error": "The showcase needs the database."}, 503)
    text = await _text_of(request)
    if text is None:
        return JSONResponse({"ok": False, "error": "Say or type something first."}, 422)
    runner = {"intake": live_intake, "dependency": live_dependency, "reply": live_reply}[name]
    async with _lock(request):
        try:
            result = await runner(factory, _env(request), text, _live_ai(request))  # type: ignore[arg-type]
        except LiveInputError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, 422)
        except ShowcaseError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, 409)
        except Exception:
            logger.info("showcase live", extra={"kind": f"showcase.live.{name}", "ok": False})
            return JSONResponse(
                {"ok": False, "error": "That moment failed. Reset and try again."}, 500
            )
        with factory() as session:  # type: ignore[operator]
            save_tour_state(session, {"live": {name: result}})
            session.commit()
    _blank_overlay(request)
    surface.live.publish(
        surface.demo_case_id,
        "showcase.step",
        {"summary": result["headline"], "step": name},
        actor="showcase",
    )
    return JSONResponse({"ok": True, **result})


@router.post("/api/showcase/live/intake")
async def live_intake_route(request: Request):
    return await _live(request, "intake")


@router.post("/api/showcase/live/dependency")
async def live_dependency_route(request: Request):
    return await _live(request, "dependency")


@router.post("/api/showcase/live/reply")
async def live_reply_route(request: Request):
    return await _live(request, "reply")


@router.post("/api/showcase/run-to")
async def showcase_run_to(request: Request):
    """Run every step up to the named one (the tour's 'Run it'). Returns that step's result."""
    denied = _require_desk(request)
    if denied is not None:
        return denied
    surface = get_surface(request)
    factory = surface.session_factory
    if factory is None:
        return JSONResponse({"ok": False, "error": "The showcase needs the database."}, 503)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    step_id = body.get("step") if isinstance(body, dict) else None
    if not isinstance(step_id, str):
        return JSONResponse({"ok": False, "error": "Name a step."}, 422)
    async with _lock(request):
        try:
            result = await run_to(factory, _env(request), step_id)  # type: ignore[arg-type]
        except ShowcaseError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, 409)
        except Exception:
            logger.info("showcase step", extra={"kind": "showcase.step", "ok": False})
            return JSONResponse(
                {"ok": False, "error": "That step failed. Reset and try again."}, 500
            )
    _blank_overlay(request)
    surface.live.publish(
        surface.demo_case_id,
        "showcase.step",
        {"summary": result.headline, "step": result.step_id},
        actor="showcase",
    )
    from dataclasses import asdict

    return JSONResponse({"ok": True, **(_step_payload(asdict(result)) or {})})


_NARRATION_KEY = "showcase_narration"
_NARRATION_MAX = 40


def _no_voice(status: int, why: str) -> JSONResponse:
    return JSONResponse({"ok": False, "fallback": "browser", "error": why}, status_code=status)


@router.post("/api/showcase/narrate")
async def showcase_narrate(request: Request):
    """Spoken narration for the autoplay demo. Cached by text; the browser falls back on error."""
    denied = _require_desk(request)
    if denied is not None:
        return denied
    text = await _text_of(request)
    if text is None:
        return JSONResponse({"ok": False, "error": "Give some text to speak."}, 422)
    ai = _live_ai(request)
    if ai is None:
        return _no_voice(503, "No speech voice is configured; the browser voice is used.")
    settings = getattr(request.app.state, "settings", None)
    voice = getattr(settings, "tts_voice", "") if settings is not None else ""
    cache: dict[str, bytes] = getattr(request.app.state, _NARRATION_KEY, None) or {}
    setattr(request.app.state, _NARRATION_KEY, cache)
    key = hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()
    audio = cache.get(key)
    if audio is None:
        try:
            chunks = [c.audio async for c in ai.speak_stream(text, audio_format="opus")]
        except Exception:
            logger.info("showcase narrate", extra={"kind": "showcase.narrate", "ok": False})
            return _no_voice(502, "The voice service was unavailable; the browser voice is used.")
        audio = b"".join(chunks)
        if not audio:
            return _no_voice(502, "The voice service returned nothing; the browser voice is used.")
        if len(cache) >= _NARRATION_MAX:
            cache.pop(next(iter(cache)))
        cache[key] = audio
    return Response(
        audio, media_type="audio/ogg", headers={"Cache-Control": "private, max-age=600"}
    )
