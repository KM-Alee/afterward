"""Emit JSON metadata to stdout with credential redaction and opt-in text logging."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
case_id_context: ContextVar[str | None] = ContextVar("case_id", default=None)
MASK = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"api.?key|token|secret|password|passcode|authorization|credential|database.?url|vault.?key",
    re.I,
)
_CONTENT_KEY = re.compile(r"transcript|body|content|text|prompt|message|email|document", re.I)
_PATTERNS = [
    re.compile(r"postgres(?:ql)?(?:\+psycopg)?://[^\s\"'<>]+", re.I),
    re.compile(r"(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"(?:sk-|gh[pousr]_|github_pat_|AIza)[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(
        r"(?i)(?:api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|token|secret|password|passcode|"
        r"authorization)\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
    ),
]


def redact(value: Any, *, log_transcripts: bool = False) -> Any:
    """Recursively redact credentials and suppress explicitly marked content fields."""
    if isinstance(value, dict):
        return {
            str(key): MASK
            if _SECRET_KEY.search(str(key))
            or (not log_transcripts and _CONTENT_KEY.search(str(key)))
            else redact(item, log_transcripts=log_transcripts)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, log_transcripts=log_transcripts) for item in value]
    if isinstance(value, str):
        for pattern in _PATTERNS:
            value = pattern.sub(MASK, value)
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # Never call repr on arbitrary SDK response or settings objects.
    return MASK


class RedactionFilter(logging.Filter):
    """Redact records before a handler can emit them, including structured extras."""

    def __init__(self, log_transcripts: bool = False):
        super().__init__()
        self.log_transcripts = log_transcripts

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage() if self.log_transcripts else "[text logging disabled]"
        record.msg = redact(message, log_transcripts=self.log_transcripts)
        record.args = ()
        for key, value in list(vars(record).items()):
            if key not in {"msg", "args", "exc_info", "exc_text", "stack_info"}:
                setattr(
                    record, key, redact({key: value}, log_transcripts=self.log_transcripts)[key]
                )
        # Exceptions can contain DSNs, request bodies and arbitrary provider replies.
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class JSONFormatter(logging.Formatter):
    """Default to a metadata allowlist; free-form content requires explicit opt-in."""

    def __init__(self, log_transcripts: bool = False):
        super().__init__()
        self.log_transcripts = log_transcripts

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "case_id": getattr(record, "case_id", case_id_context.get()),
            "kind": getattr(record, "kind", "runtime"),
        }
        for key in ("status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if self.log_transcripts:
            payload["message"] = record.getMessage()
            payload["data"] = getattr(record, "data", {})
        return json.dumps(redact(payload, log_transcripts=self.log_transcripts), ensure_ascii=True)


def configure_logging(log_transcripts: bool = False) -> None:
    """Replace application/server handlers so stdout uses one safe JSON format."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactionFilter(log_transcripts))
    handler.setFormatter(JSONFormatter(log_transcripts))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore", "sqlalchemy"):
        child = logging.getLogger(name)
        child.handlers.clear()
        child.propagate = True
