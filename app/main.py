"""Running application: health, the approved pages, and background health checks."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.call.router import router as call_router
from app.config import Settings, postgres_url
from app.db import init_db, make_engine
from app.logging import case_id_context, configure_logging, request_id_context
from app.runtime import handle_telegram, supervise
from app.web.router import router as web_router
from app.web.state import build_surface

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

# Uvicorn emits startup records before entering lifespan; keep those JSON as well.
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    configure_logging(settings.log_transcripts)
    app.state.settings = settings
    database_url = settings.database_url.get_secret_value()
    app.state.surface = build_surface(
        settings.demo_passcode.get_secret_value(),
        phone_calls_enabled=settings.phone_calls_enabled,
    )
    if _mail_configured(settings):
        app.state.surface.cases[app.state.surface.demo_case_id].monitoring = "ok"
    app.state.run_proofs_live = bool(database_url)
    stop = asyncio.Event()
    worker = None
    if database_url:
        try:
            init_db(make_engine(database_url))
            from app.web.snapshot import attach_snapshot

            attach_snapshot(app.state.surface, database_url)
            logger.info("database bootstrap", extra={"kind": "db.bootstrap", "ok": True})
            worker = asyncio.create_task(supervise(stop, database_url, settings.poll_seconds))
        except Exception:
            logger.info("database bootstrap", extra={"kind": "db.bootstrap", "ok": False})
            app.state.run_proofs_live = False
    try:
        app.state.surface.live.attach(asyncio.get_running_loop())
    except Exception:
        logger.info("event hub", extra={"kind": "web.live", "ok": False})
    yield
    stop.set()
    if worker is not None:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(web_router)
app.include_router(call_router)
app.add_api_route("/webhooks/telegram", handle_telegram, methods=["POST"])
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = uuid4().hex
    request_token = request_id_context.set(request_id)
    case_token = case_id_context.set(None)
    started = time.monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            "request finished",
            extra={
                "kind": "http.request",
                "status_code": status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        request_id_context.reset(request_token)
        case_id_context.reset(case_token)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def database_reachable(settings: Settings) -> bool:
    """Probe without printing a DSN or driver exception, including on failure."""
    if not settings.database_url.get_secret_value():
        return False
    engine = None
    try:
        engine = create_engine(
            postgres_url(settings.database_url.get_secret_value()),
            poolclass=NullPool,
            connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
        )
        with engine.connect() as connection:
            return connection.scalar(text("SELECT 1")) == 1
    except Exception:
        return False
    finally:
        if engine is not None:
            engine.dispose()


@app.get("/status")
def status(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "models": {
            "stt": settings.stt_model,
            "fast": settings.llm_fast_model,
            "accurate": settings.llm_accurate_model,
            "tts": settings.tts_model,
            "realtime": settings.realtime_model,
        },
        "channels": {
            "telegram": settings.telegram_mode,
            "whatsapp": "webhook" if settings.whatsapp_token.get_secret_value() else "disabled",
        },
        "mail": "configured" if _mail_configured(settings) else "disabled",
        "phone_calls": "enabled" if settings.phone_calls_enabled else "disabled",
        "db_reachable": database_reachable(settings),
    }


def _mail_configured(settings: Settings) -> bool:
    """True when the family mailbox has an address and a refresh token. No token is read out."""
    return bool(
        settings.family_mailbox
        and settings.google_client_id.get_secret_value()
        and settings.google_refresh_token_family.get_secret_value()
    )
