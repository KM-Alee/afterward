"""Autopilot and the three pause controls. Checked again at execution, not at approval time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.models import Autopilot, CaseControl

Effect = Literal["allow", "deny", "ask"]
_CONSEQUENTIAL = {"close", "transfer", "freeze"}


@dataclass(frozen=True)
class PolicyDecision:
    """`ask` means the family must already have approved. `deny` cancels the job."""

    effect: Effect
    reason: str


def _control(case: object) -> CaseControl:
    value = case.control
    return value if isinstance(value, CaseControl) else CaseControl(value)


def _autopilot(case: object) -> Autopilot:
    value = case.autopilot
    return value if isinstance(value, Autopilot) else Autopilot(value)


def decide(
    case: object,
    *,
    job_kind: str,
    outbound: bool,
    touches_family: bool,
    deadline_notice: bool,
    action: str | None,
    routine: bool,
    at: datetime,
) -> PolicyDecision:
    """Quiet stops family messages. Hold stops outbound work. Stop stops everything."""
    control = _control(case)
    if control is CaseControl.stopped:
        return PolicyDecision("deny", "stopped")
    if control is CaseControl.hold and outbound:
        return PolicyDecision("deny", "hold")
    if control is CaseControl.quiet_until and touches_family:
        quiet_until = getattr(case, "quiet_until", None)
        quiet_active = quiet_until is None or at < quiet_until
        if quiet_active and not (deadline_notice and getattr(case, "deadline_during_quiet", False)):
            return PolicyDecision("deny", "quiet")
    autopilot = _autopilot(case)
    if autopilot is Autopilot.gentle and job_kind == "followup":
        return PolicyDecision("ask", "approval_required")
    if autopilot is Autopilot.steady and job_kind == "followup":
        return PolicyDecision("allow", "")
    if routine and autopilot is Autopilot.steady and job_kind == "send_request":
        return PolicyDecision("allow", "")
    if outbound or (action or "") in _CONSEQUENTIAL:
        return PolicyDecision("ask", "approval_required")
    return PolicyDecision("allow", "")
