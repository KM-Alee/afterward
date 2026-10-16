"""Mailbox health notices. Payloads name a reason and carry no secrets."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.contracts import SqlEventBus
from app.mail.health import MailboxWatch, apply_mailbox_health, health_reason
from app.models import Event, Monitoring
from tests.mail.support import malik

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def test_poll_age_and_token_validity_choose_the_reason():
    fresh = MailboxWatch(last_poll_at=NOW - timedelta(minutes=10), token_valid=True)
    assert health_reason(fresh, now=NOW) is None
    stale = MailboxWatch(last_poll_at=NOW - timedelta(minutes=10, seconds=1), token_valid=True)
    assert health_reason(stale, now=NOW) == "poll_stale"
    invalid = MailboxWatch(last_poll_at=NOW, token_valid=False)
    assert health_reason(invalid, now=NOW) == "token_invalid"
    assert health_reason(MailboxWatch(token_valid=True), now=NOW) == "poll_stale"


@pytest.mark.db
def test_interrupted_monitoring_publishes_one_family_notice(db_session):
    case = malik(db_session)
    bus = SqlEventBus()
    watch = MailboxWatch(last_poll_at=NOW, token_valid=False)
    reason = apply_mailbox_health(db_session, case, bus, watch, now=NOW)
    assert reason == "token_invalid"
    assert case.monitoring == Monitoring.interrupted
    apply_mailbox_health(db_session, case, bus, watch, now=NOW)
    events = list(db_session.scalars(select(Event).where(Event.kind == "monitoring")))
    assert len(events) == 1
    assert events[0].payload == {"monitoring": "interrupted", "reason": "token_invalid"}
    assert events[0].actor == "Afterward"
    assert "secret" not in events[0].payload

    watch.token_valid = True
    watch.last_poll_at = NOW
    assert apply_mailbox_health(db_session, case, bus, watch, now=NOW) is None
    assert case.monitoring == Monitoring.ok
    restored = list(db_session.scalars(select(Event).where(Event.kind == "monitoring")))
    assert len(restored) == 2
    assert restored[1].payload == {"monitoring": "ok", "reason": "poll_ok"}
