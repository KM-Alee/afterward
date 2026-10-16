"""Browser call room. A browser call is not a phone call."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "router":
        from app.call.router import router

        return router
    raise AttributeError(name)


__all__ = ["router"]
