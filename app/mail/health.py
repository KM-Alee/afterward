"""Mailbox health. A stale poll or an invalid token interrupts monitoring.

The family notice names the reason code. It does not carry tokens or mail text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.contracts import EventBus
from app.models import Case, Monitoring

DEFAULT_MAX_POLL_AGE = timedelta(minutes=10)


@dataclass
class MailboxWatch:
    """Last successful poll and whether the refresh token is present."""

    last_poll_at: datetime | None = None
    token_valid: bool = True


def health_reason(
    watch: MailboxWatch,
    *,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_POLL_AGE,
) -> str | None:
    """Return a reason code when monitoring should be interrupted."""
    if not watch.token_valid:
        return "token_invalid"
    if watch.last_poll_at is None or now - watch.last_poll_at > max_age:
        return "poll_stale"
    return None


def apply_mailbox_health(
    session: Session,
    case: Case,
    bus: EventBus,
    watch: MailboxWatch,
    *,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_POLL_AGE,
) -> str | None:
    """Set monitoring and publish one family notice when the state changes."""
    reason = health_reason(watch, now=now, max_age=max_age)
    if reason is not None:
        if case.monitoring != Monitoring.interrupted:
            case.monitoring = Monitoring.interrupted
            bus.publish(
                session,
                case.id,
                "monitoring",
                {"monitoring": "interrupted", "reason": reason},
                actor="Afterward",
            )
        return reason
    if case.monitoring != Monitoring.ok:
        case.monitoring = Monitoring.ok
        bus.publish(
            session,
            case.id,
            "monitoring",
            {"monitoring": "ok", "reason": "poll_ok"},
            actor="Afterward",
        )
    return None
