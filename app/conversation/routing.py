"""Deterministic routing. Code chooses the path; the model does not grant a permission."""

import re

_CRISIS = re.compile(
    r"\b(suicide|kill myself|end my life|want to die|self-harm|hurt myself"
    r"|can't go on|cannot go on)\b",
    re.I,
)
_START = re.compile(r"^/start(?:@\w+)?(?:\s+(\S+))?\s*$", re.I)
_COMMAND = re.compile(r"^/(status|quiet|hold|stop|resume|help)(?:@\w+)?\s*$", re.I)
_COMMANDS = frozenset({"status", "quiet", "hold", "stop", "resume", "help"})
_OFF_TOPIC = (
    "weather",
    "joke",
    "recipe",
    "football",
    "homework",
    "poem",
    "bitcoin",
    "stock price",
    "play a game",
)
_DECISIONS = (
    "whatever you think",
    "just keep",
    "keep mum",
    "close the",
    "close it",
    "transfer it",
    "cancel the",
    "don't close",
    "do not close",
)


def is_crisis(text: str) -> bool:
    return _CRISIS.search(text) is not None


def parse_start(text: str) -> str | None:
    """Invite token, or "" for a bare /start. None when the text is not a start command."""
    match = _START.match(text.strip())
    if match is None:
        return None
    return match.group(1) or ""


def parse_command(text: str) -> str | None:
    stripped = text.strip()
    match = _COMMAND.match(stripped)
    if match is not None:
        return match.group(1).lower()
    bare = stripped.lower()
    if bare in _COMMANDS:
        return bare
    return None


def is_off_topic(text: str) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in _OFF_TOPIC)


def is_finish_question(text: str) -> bool:
    lowered = text.lower()
    return "did you finish" in lowered or "finish everything" in lowered


def is_decision(text: str) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in _DECISIONS)


def is_question(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered.endswith("?"):
        return True
    return lowered.startswith(("what ", "when ", "where ", "who ", "how ", "which ", "did you"))
