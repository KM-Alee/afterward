"""Family controls: quiet, hold, stop and resume. Each one means something different."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.conversation.case_link import mirror_controls


@dataclass
class Controls:
    """In-memory control flags. The engine applies the same meanings to the case row."""

    control: str = "active"
    quiet_until: datetime | None = None
    monitoring: bool = True
    org_actions: bool = True


def apply_command(controls: Controls, name: str, now: datetime) -> str:
    """Update controls and return the reply. `resume` is the way back from stop."""
    if name == "quiet":
        controls.control = "quiet_until"
        controls.quiet_until = now + timedelta(hours=24)
        controls.monitoring = True
        controls.org_actions = True
        mirror_controls(controls.control, controls.quiet_until)
        return (
            "I'll stay quiet for 24 hours. Monitoring continues, and I won't start new messages "
            "until then. Reply if you need me."
        )
    if name == "hold":
        controls.control = "hold"
        controls.quiet_until = None
        controls.monitoring = True
        controls.org_actions = False
        mirror_controls(controls.control, controls.quiet_until)
        return "I'll hold outgoing requests to organisations. Monitoring continues."
    if name == "stop":
        controls.control = "stopped"
        controls.quiet_until = None
        controls.monitoring = False
        controls.org_actions = False
        mirror_controls(controls.control, controls.quiet_until)
        return (
            "I've stopped the case, including monitoring. Say resume when you want to continue. "
            "I can still hear resume and help."
        )
    if name == "resume":
        controls.control = "active"
        controls.quiet_until = None
        controls.monitoring = True
        controls.org_actions = True
        mirror_controls(controls.control, controls.quiet_until)
        return "I'm active again. Monitoring is on."
    if name == "help":
        return (
            "I can help with this case. Commands: status, quiet, hold, stop, resume, help. "
            "Quiet pauses messages to you for 24 hours. Hold stops requests to organisations. "
            "Stop pauses the case, including monitoring."
        )
    return status_text(controls, None)


def status_text(controls: Controls, snapshot: Mapping[str, object] | None) -> str:
    """Say the control state and only the snapshot fields the caller supplied."""
    lines = [f"Case control: {controls.control}."]
    if not controls.monitoring:
        lines.append("Monitoring is stopped.")
    elif controls.control == "hold":
        lines.append("Outgoing requests to organisations are held. Monitoring continues.")
    elif controls.control == "quiet_until":
        lines.append("Messages stay quiet. Monitoring continues.")
    if not snapshot:
        lines.append("I don't have an account summary yet.")
        return " ".join(lines)
    for key in ("accounts", "open_requests"):
        if key in snapshot:
            lines.append(f"{key}: {snapshot[key]}.")
    return " ".join(lines)
