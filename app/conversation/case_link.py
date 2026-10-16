"""Mirror family control commands onto live case rows.

The conversation object is in memory. A hold, quiet, stop or resume still has
to change the case the job queue reads, or a queued send keeps going.
"""

from __future__ import annotations

from datetime import datetime

from app.case_registry import live_cases
from app.models import CaseControl, Monitoring

_CONTROL = {
    "active": CaseControl.active,
    "hold": CaseControl.hold,
    "quiet_until": CaseControl.quiet_until,
    "stopped": CaseControl.stopped,
}


def mirror_controls(control: str, quiet_until: datetime | None) -> None:
    """Copy the conversation control onto every case still in memory."""
    mapped = _CONTROL.get(control)
    if mapped is None:
        return
    for case in live_cases():
        case.control = mapped
        case.quiet_until = quiet_until
        if mapped is CaseControl.stopped:
            case.monitoring = Monitoring.interrupted
        elif mapped is CaseControl.active:
            case.monitoring = Monitoring.ok
