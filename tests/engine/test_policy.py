"""Gentle and steady autopilot, and quiet, hold and stop."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.engine.policy import decide
from app.models import Autopilot, CaseControl

NOW = datetime(2026, 4, 2, 9, tzinfo=UTC)


def _case(**overrides):
    values = {
        "control": CaseControl.active,
        "autopilot": Autopilot.gentle,
        "quiet_until": None,
        "deadline_during_quiet": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _decide(case, **overrides):
    payload = {
        "job_kind": "digest",
        "outbound": False,
        "touches_family": False,
        "deadline_notice": False,
        "action": None,
        "routine": False,
        "at": NOW,
    }
    payload.update(overrides)
    return decide(case, **payload)


def test_stop_hold_and_quiet():
    stopped = _decide(_case(control=CaseControl.stopped), job_kind="health_check")
    assert stopped.reason == "stopped"
    held = _decide(_case(control=CaseControl.hold), job_kind="send_request", outbound=True)
    assert held.reason == "hold"
    assert _decide(_case(control=CaseControl.hold), job_kind="inbox_poll").effect == "allow"
    quiet = _case(control=CaseControl.quiet_until, quiet_until=NOW + timedelta(hours=1))
    assert _decide(quiet, job_kind="digest", touches_family=True).reason == "quiet"
    assert _decide(quiet, job_kind="send_request", outbound=True).effect == "ask"
    expired = _case(control=CaseControl.quiet_until, quiet_until=NOW - timedelta(minutes=1))
    assert _decide(expired, job_kind="digest", touches_family=True).effect == "allow"


def test_deadline_during_quiet():
    quiet = _case(
        control=CaseControl.quiet_until,
        quiet_until=NOW + timedelta(hours=1),
        deadline_during_quiet=True,
    )
    allowed = _decide(quiet, job_kind="digest", touches_family=True, deadline_notice=True)
    assert allowed.effect == "allow"
    silent = _case(
        control=CaseControl.quiet_until,
        quiet_until=NOW + timedelta(hours=1),
        deadline_during_quiet=False,
    )
    denied = _decide(silent, job_kind="digest", touches_family=True, deadline_notice=True)
    assert denied.reason == "quiet"


def test_gentle_asks_and_steady_follows_up():
    gentle = _case(autopilot=Autopilot.gentle)
    steady = _case(autopilot=Autopilot.steady)
    assert _decide(gentle, job_kind="followup", outbound=True).effect == "ask"
    assert _decide(steady, job_kind="followup", outbound=True).effect == "allow"
    assert _decide(steady, job_kind="send_request", outbound=True, action="close").effect == "ask"
    routine = _decide(steady, job_kind="send_request", outbound=True, routine=True)
    assert routine.effect == "allow"
    assert _decide(gentle, job_kind="digest", touches_family=True).effect == "allow"
