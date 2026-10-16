"""Google Calendar inserts behind the same action executor as mail.

`events.insert` uses reminder overrides. Tests pass a transport and do not
call Google.
"""

from __future__ import annotations

from typing import Any, Protocol


class CalendarTransport(Protocol):
    """Insert one event and return its id."""

    def insert_event(self, body: dict[str, Any]) -> str: ...


def calendar_body(request: dict[str, object]) -> dict[str, object]:
    """Build an events.insert body from a redacted action request."""
    reminders = request.get("reminders")
    overrides: list[object]
    if isinstance(reminders, list) and reminders:
        overrides = list(reminders)
    else:
        overrides = [{"method": "popup", "minutes": 60}]
    return {
        "summary": str(request.get("summary") or "Afterward check"),
        "start": {"dateTime": str(request.get("start") or "")},
        "end": {"dateTime": str(request.get("end") or "")},
        "reminders": {"useDefault": False, "overrides": overrides},
    }


class GoogleCalendarTransport:
    """Live Calendar API. The service is built on the first insert, not at import."""

    def __init__(self, credentials: object) -> None:
        self._credentials = credentials
        self._service: Any = None

    def __repr__(self) -> str:
        return "GoogleCalendarTransport(redacted)"

    def insert_event(self, body: dict[str, Any]) -> str:
        created = self._api().events().insert(calendarId="primary", body=body).execute()
        return str(created.get("id") or "")

    def _api(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            self._service = build(
                "calendar", "v3", credentials=self._credentials, cache_discovery=False
            )
        return self._service
