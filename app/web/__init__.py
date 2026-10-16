"""Desk, family, provider, proofs and landing pages."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "router":
        from app.web.router import router

        return router
    raise AttributeError(name)


__all__ = ["router"]
