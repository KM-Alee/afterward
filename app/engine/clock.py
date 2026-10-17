"""Demo case clock. Only demo cases may move; the offset makes due jobs fire via the runner."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.errors import EngineError
from app.models import Case, Event

MAX_ADVANCE_SECONDS = 400 * 24 * 3600


def advance_case_clock(session: Session, case_id: UUID, seconds: int) -> int:
    """Move a demo case forward and return the new offset. Real cases cannot be moved."""
    case = session.get(Case, case_id)
    if case is None:
        raise EngineError("case_missing")
    if not case.is_demo:
        raise EngineError("clock_demo_only")
    if seconds <= 0 or seconds > MAX_ADVANCE_SECONDS:
        raise EngineError("clock_range")
    case.clock_offset_s = int(case.clock_offset_s) + int(seconds)
    session.add(
        Event(
            case_id=case.id,
            kind="clock.advanced",
            actor="demo",
            payload={"seconds": int(seconds), "offset_s": case.clock_offset_s},
        )
    )
    session.flush()
    return case.clock_offset_s
