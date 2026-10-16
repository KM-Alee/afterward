"""A movable wall clock. Case time adds `clock_offset_s` and nothing else."""

from datetime import UTC, datetime, timedelta

from app.contracts import CaseClock


class FakeClock:
    """Wall time under test control. The offset is read from the case, not stored here."""

    def __init__(self, wall: datetime | None = None) -> None:
        starting = wall or datetime(2026, 3, 6, 9, 0, tzinfo=UTC)
        if starting.tzinfo is None:
            raise ValueError("FakeClock requires a timezone-aware wall time")
        self.wall = starting

    def case_now(self, case: CaseClock) -> datetime:
        return self.wall + timedelta(seconds=int(case.clock_offset_s))

    def advance(self, **delta: float) -> None:
        self.wall += timedelta(**delta)
