"""Weak references to case rows created in this process. No model imports."""

from __future__ import annotations

import weakref
from typing import Any

_LIVE: set[weakref.ref[Any]] = set()


def remember(case: Any) -> None:
    """Track a case so a later family command can update the same object."""
    _LIVE.add(weakref.ref(case))


def live_cases() -> list[Any]:
    """Return cases that have not been garbage-collected."""
    found: list[Any] = []
    dead: list[weakref.ref[Any]] = []
    for ref in _LIVE:
        case = ref()
        if case is None:
            dead.append(ref)
        else:
            found.append(case)
    for ref in dead:
        _LIVE.discard(ref)
    return found
