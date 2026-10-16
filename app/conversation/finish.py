"""Warm wording for a completion summary. Counts come only from the supplied dict."""

from collections.abc import Mapping

_LABELS = {
    "confirmed": "confirmed with written evidence",
    "promised": "promised but not yet evidenced",
    "blocked": "blocked",
    "handed_back": "handed back to you",
    "unconfirmed": "candidate accounts still unconfirmed",
}
_ORDER = ("confirmed", "promised", "blocked", "handed_back", "unconfirmed")


def finish_reply(summary: Mapping[str, object] | None) -> str:
    """Rephrase `summary`. Missing keys are omitted, and nothing is called finished."""
    if not summary:
        return "I don't have a completion summary yet, so I can't say this is finished."
    lines: list[str] = []
    for key in _ORDER:
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        count = summary[key]
        label = _LABELS[key]
        if key == "blocked" and isinstance(summary.get("blocked_reason"), str):
            label = f"blocked until {summary['blocked_reason']}"
        if key == "handed_back" and isinstance(summary.get("handed_back_reason"), str):
            label = f"handed to you ({summary['handed_back_reason']})"
        lines.append(f"{count} {label}.")
    if not lines:
        return "That summary has no completion figures, so I can't say this is finished."
    detail = " ".join(lines)
    return f"I wouldn't call this finished. Here is what the records show: {detail}"
