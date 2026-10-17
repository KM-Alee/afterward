"""Database access for the web layer. No database means the labelled in-memory demo."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]


def session_factory_for(app: Any) -> SessionFactory | None:
    """A factory of sessions, or None when no database is configured.

    `app.state.session_factory` wins (tests and embedding). Otherwise the engine is built once
    from the configured URL and cached on the app.
    """
    custom = getattr(app.state, "session_factory", None)
    if custom is not None:
        return custom
    cached = getattr(app.state, "web_session_factory", None)
    if cached is not None:
        return cached
    settings = getattr(app.state, "settings", None)
    url = settings.database_url.get_secret_value() if settings is not None else ""
    if not url:
        return None
    from app.db import make_engine

    engine = make_engine(url)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session

    app.state.web_session_factory = factory
    return factory
