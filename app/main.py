"""Minimal infrastructure shell with liveness and non-secret configuration status."""

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import Settings, postgres_url
from app.db import init_db, make_engine
from app.logging import case_id_context, configure_logging, request_id_context

# Uvicorn emits startup records before entering lifespan; keep those JSON as well.
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    configure_logging(settings.log_transcripts)
    app.state.settings = settings
    database_url = settings.database_url.get_secret_value()
    if database_url:
        try:
            init_db(make_engine(database_url))
            logger.info("database bootstrap", extra={"kind": "db.bootstrap", "ok": True})
        except Exception:
            logger.info("database bootstrap", extra={"kind": "db.bootstrap", "ok": False})
    # The job worker is wired in Phase 3. This process only boots the schema.
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


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
        "phone_calls": "enabled" if settings.phone_calls_enabled else "disabled",
        "db_reachable": database_reachable(settings),
    }
