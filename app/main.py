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
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.call.router import router as call_router
from app.config import Settings, postgres_url
from app.db import init_db, make_engine
from app.engine.demo_case import ensure_demo_case
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
    # Monitoring is reported by the inbox_poll job after a real poll, never from config alone.
    app.state.run_proofs_live = bool(database_url)
    stop = asyncio.Event()
    worker = None
    if database_url:
        try:
            init_db(make_engine(database_url))
            from app.web.snapshot import attach_snapshot

            attach_snapshot(app.state.surface, database_url)
            logger.info("database bootstrap", extra={"kind": "db.bootstrap", "ok": True})
            _seed_demo_case(
                database_url, settings.providers_mailbox, start_poll=_mail_configured(settings)
            )
            worker = asyncio.create_task(
                supervise(stop, database_url, settings.poll_seconds, app=app, settings=settings)
            )
            _restore_conversation(app, settings)
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


def _restore_conversation(app: FastAPI, settings: Settings) -> None:
    """Load the saved Telegram conversation at boot, so a restart resumes the case."""
    if not settings.telegram_bot_token.get_secret_value():
        return
    try:
        from app.runtime import _conversation

        app.state.conversation = _conversation(settings)
    except Exception:
        logger.info("conversation restore", extra={"kind": "conversation.restore", "ok": False})


def _seed_demo_case(database_url: str, providers_mailbox: str, *, start_poll: bool) -> None:
    """Insert the demo case once and start its inbox poll when mail is configured.

    A failure is logged by kind and never stops boot.
    """
    engine = make_engine(database_url)
    try:
        with Session(engine) as session:
            case_id = ensure_demo_case(session, providers_mailbox=providers_mailbox)
            if start_poll:
                from app.mail.jobs import ensure_inbox_poll

                ensure_inbox_poll(session, case_id)
            session.commit()
    except Exception:
        logger.info("demo seed", extra={"kind": "db.seed", "ok": False})
    finally:
        engine.dispose()


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
            # WhatsApp is out of this build: no webhook route is mounted (ADR-012).
            "whatsapp": "disabled",
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
