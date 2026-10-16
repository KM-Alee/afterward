"""Local app the tests use. The lead mounts the routers on `app.main` in Phase 3."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.call.router import router as call_router
from app.web.router import router as web_router
from app.web.state import build_surface

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def create_surface_app(*, demo_passcode: str, phone_calls_enabled: bool = False) -> FastAPI:
    """Pages and the call room, with an in-memory demo case."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        app.state.surface.live.attach(asyncio.get_running_loop())
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.surface = build_surface(demo_passcode, phone_calls_enabled=phone_calls_enabled)
    app.include_router(web_router)
    app.include_router(call_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
