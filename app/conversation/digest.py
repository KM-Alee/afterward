"""Weekly digest. Quiet days and a stopped case produce no message."""

from collections.abc import Sequence
from datetime import date, datetime


def weekly_digest(
    lines: Sequence[str],
    *,
    on: date,
    quiet_days: set[date],
    quiet_until: datetime | None,
    stopped: bool,
) -> str | None:
    """Return the digest, or None when this day should stay quiet."""
    if stopped or on in quiet_days:
        return None
    if quiet_until is not None and on <= quiet_until.date():
        return None
    body = "\n".join(f"• {line}" for line in lines) if lines else "Nothing urgent this week."
    return f"This week:\n{body}"
