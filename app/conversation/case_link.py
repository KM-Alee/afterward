"""Mirror family control commands onto live case rows.

The conversation object is in memory. A hold, quiet, stop or resume still has
to change the case the job queue reads, or a queued send keeps going.
"""

from __future__ import annotations

import weakref
from datetime import datetime

from app.models import Case, CaseControl, Monitoring

_LIVE: set[weakref.ref[Case]] = set()

_CONTROL = {
    "active": CaseControl.active,
    "hold": CaseControl.hold,
    "quiet_until": CaseControl.quiet_until,
    "stopped": CaseControl.stopped,
}


def remember_case(case: Case) -> None:
    """Keep a weak reference so a later family command can reach this row."""
    _LIVE.add(weakref.ref(case))


def mirror_controls(control: str, quiet_until: datetime | None) -> None:
    """Copy the conversation control onto every case still in memory."""
    mapped = _CONTROL.get(control)
    if mapped is None:
        return
    dead: list[weakref.ref[Case]] = []
    for ref in _LIVE:
        case = ref()
        if case is None:
            dead.append(ref)
            continue
        case.control = mapped
        case.quiet_until = quiet_until
        if mapped is CaseControl.stopped:
            case.monitoring = Monitoring.interrupted
        elif mapped is CaseControl.active:
            case.monitoring = Monitoring.ok
    for ref in dead:
        _LIVE.discard(ref)
