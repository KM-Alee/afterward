"""Save and reload the demo desk so a process restart keeps the story."""

from __future__ import annotations

import logging
from dataclasses import asdict
from uuid import UUID

from app.call.acceptance import CallRoom, OfferedTerms, Turn
from app.contracts import SentRecord
from app.fakes import FakeCallSession
from app.web.state import (
    AccountTile,
    CaseBoard,
    Check,
    ClockCase,
    Dim,
    OutcomePanel,
    ProviderThread,
    SurfaceState,
    TimelineEvent,
)

logger = logging.getLogger(__name__)
SNAPSHOT_ID = "demo"


def dump_surface(surface: SurfaceState) -> dict[str, object]:
    """JSON-ready desk state. Login cookies and call audio stay out."""
    return {
        "family_tokens": {key: str(value) for key, value in surface.family_tokens.items()},
        "provider_tokens": {key: str(value) for key, value in surface.provider_tokens.items()},
        "call_tokens": {key: str(value) for key, value in surface.call_tokens.items()},
        "cases": {str(key): _board(value) for key, value in surface.cases.items()},
        "calls": {key: _call(value) for key, value in surface.calls.items()},
        "sent": [record.model_dump() for record in surface.mailbox.sent],
        "sessions": sorted(surface.sessions),
    }


def load_surface(surface: SurfaceState, payload: dict[str, object]) -> None:
    """Replace the live desk with a snapshot. Passcode and sockets stay as they are."""
    surface.family_tokens = _token_map(payload.get("family_tokens"))
    surface.provider_tokens = _token_map(payload.get("provider_tokens"))
    surface.call_tokens = _token_map(payload.get("call_tokens"))
    cases = payload.get("cases")
    if isinstance(cases, dict) and cases:
        surface.cases = {UUID(key): _board_from(value) for key, value in cases.items()}
    calls = payload.get("calls")
    surface.calls = {}
    if isinstance(calls, dict):
        for key, value in calls.items():
            if isinstance(value, dict):
                surface.calls[key] = _call_from(value)
    sent = payload.get("sent")
    surface.mailbox.sent = []
    if isinstance(sent, list):
        for item in sent:
            if isinstance(item, dict):
                surface.mailbox.sent.append(SentRecord.model_validate(item))
    sessions = payload.get("sessions")
    if isinstance(sessions, list):
        surface.sessions = {str(item) for item in sessions}


def attach_snapshot(surface: SurfaceState, database_url: str) -> None:
    """Load a saved desk, then write it back after each published change."""
    if not database_url:
        return
    stored = _read(database_url)
    if stored is not None:
        try:
            load_surface(surface, stored)
        except Exception:
            logger.info("desk snapshot", extra={"kind": "desk.snapshot", "ok": False})

    def _save() -> None:
        try:
            _write(database_url, dump_surface(surface))
        except Exception:
            logger.info("desk snapshot", extra={"kind": "desk.snapshot", "ok": False})

    surface.live.on_change = _save


def _board(board: CaseBoard) -> dict[str, object]:
    payload = asdict(board)
    payload["id"] = str(board.id)
    return payload


def _call(room: CallRoom) -> dict[str, object]:
    terms = asdict(room.terms) if room.terms is not None else None
    return {
        "terms": terms,
        "terms_hash": room.terms_hash,
        "approved_hash": room.approved_hash,
        "approval_status": room.approval_status,
        "sentence": room.sentence,
        "turns": [asdict(turn) for turn in room.turns],
        "acceptance_played": room.acceptance_played,
        "status": room.status,
    }


def _token_map(raw: object) -> dict[str, UUID]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): UUID(str(value)) for key, value in raw.items()}


def _board_from(raw: object) -> CaseBoard:
    if not isinstance(raw, dict):
        raise ValueError("desk case snapshot was not an object")
    outcome = raw.get("outcome")
    return CaseBoard(
        id=UUID(str(raw["id"])),
        deceased=str(raw["deceased"]),
        died=str(raw["died"]),
        handler=str(raw["handler"]),
        empty=bool(raw["empty"]),
        is_demo=bool(raw["is_demo"]),
        clock_case=ClockCase(clock_offset_s=int(raw["clock_case"]["clock_offset_s"])),
        monitoring=str(raw["monitoring"]),
        delivery=str(raw["delivery"]),
        accounts=[_account(item) for item in raw.get("accounts", [])],
        outcome=_outcome(outcome) if isinstance(outcome, dict) else None,
        events=[_event(item) for item in raw.get("events", [])],
        threads={
            str(key): _thread(value)
            for key, value in raw.get("threads", {}).items()
            if isinstance(value, dict)
        },
        family_choice=raw.get("family_choice"),
    )


def _account(raw: dict[str, object]) -> AccountTile:
    return AccountTile(
        id=str(raw["id"]),
        name=str(raw["name"]),
        label=str(raw["label"]),
        origin=str(raw["origin"]),
        bucket_kind=str(raw["bucket_kind"]),
        bucket_text=str(raw["bucket_text"]),
        service=_dim(raw["service"]),
        money=_dim(raw["money"]),
        docs=_dim(raw["docs"]),
        next_owner=str(raw["next_owner"]),
        next_action=str(raw["next_action"]),
        focus=bool(raw.get("focus")),
        conditions=[_check(item) for item in raw.get("conditions", []) if isinstance(item, dict)],
    )


def _dim(raw: object) -> Dim:
    if not isinstance(raw, dict):
        return Dim("neutral", "")
    return Dim(str(raw.get("kind") or "neutral"), str(raw.get("text") or ""))


def _check(raw: dict[str, object]) -> Check:
    return Check(
        str(raw.get("label") or ""),
        str(raw.get("chip_kind") or "unknown"),
        str(raw.get("chip_text") or ""),
        str(raw.get("why") or ""),
    )


def _event(raw: object) -> TimelineEvent:
    if not isinstance(raw, dict):
        return TimelineEvent("", "", "unverified", "system")
    return TimelineEvent(
        str(raw.get("text") or ""),
        str(raw.get("at") or ""),
        str(raw.get("evidence") or "unverified"),
        str(raw.get("tone") or "system"),
        str(raw.get("quote") or ""),
    )


def _outcome(raw: dict[str, object]) -> OutcomePanel:
    return OutcomePanel(
        title=str(raw.get("title") or ""),
        plan_version=int(raw.get("plan_version") or 1),
        requested=str(raw.get("requested") or ""),
        requested_conditions=[str(item) for item in raw.get("requested_conditions", [])],
        quote=str(raw.get("quote") or ""),
        quote_evidence=str(raw.get("quote_evidence") or "writing"),
        quote_at=str(raw.get("quote_at") or ""),
        verdict_kind=str(raw.get("verdict_kind") or "notdone"),
        verdict_text=str(raw.get("verdict_text") or ""),
        checks=[_check(item) for item in raw.get("checks", []) if isinstance(item, dict)],
    )


def _thread(raw: dict[str, object]) -> ProviderThread:
    replies = raw.get("replies")
    return ProviderThread(
        str(raw.get("provider") or ""),
        str(raw.get("subject") or ""),
        str(raw.get("request_body") or ""),
        replies=[item for item in replies if isinstance(item, dict)]
        if isinstance(replies, list)
        else [],
    )


def _call_from(raw: dict[str, object]) -> CallRoom:
    terms_raw = raw.get("terms")
    terms = OfferedTerms(**terms_raw) if isinstance(terms_raw, dict) else None
    turns = []
    for item in raw.get("turns", []):
        if isinstance(item, dict):
            turns.append(
                Turn(
                    who=str(item.get("who") or ""),
                    text=str(item.get("text") or ""),
                    via=str(item.get("via") or ""),
                    kind=str(item.get("kind") or ""),
                )
            )
    return CallRoom(
        session=FakeCallSession(),
        terms=terms,
        terms_hash=raw.get("terms_hash") if isinstance(raw.get("terms_hash"), str) else None,
        approved_hash=raw.get("approved_hash")
        if isinstance(raw.get("approved_hash"), str)
        else None,
        approval_status=str(raw.get("approval_status") or "none"),
        sentence=raw.get("sentence") if isinstance(raw.get("sentence"), str) else None,
        turns=turns,
        acceptance_played=bool(raw.get("acceptance_played")),
        status=str(raw.get("status") or "ready"),
    )


def _read(database_url: str) -> dict[str, object] | None:
    from sqlalchemy.orm import Session

    from app.db import make_engine
    from app.models import DeskSnapshot

    engine = make_engine(database_url)
    try:
        with Session(engine) as session:
            row = session.get(DeskSnapshot, SNAPSHOT_ID)
            if row is None or not isinstance(row.payload, dict):
                return None
            return row.payload
    finally:
        engine.dispose()


def _write(database_url: str, payload: dict[str, object]) -> None:
    from sqlalchemy.orm import Session

    from app.db import make_engine
    from app.models import DeskSnapshot

    engine = make_engine(database_url)
    try:
        with Session(engine) as session:
            row = session.get(DeskSnapshot, SNAPSHOT_ID)
            if row is None:
                session.add(DeskSnapshot(id=SNAPSHOT_ID, payload=payload))
            else:
                row.payload = payload
            session.commit()
    finally:
        engine.dispose()
