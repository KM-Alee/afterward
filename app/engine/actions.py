"""Outbound effects. Uncertain delivery is reconciled and never blindly retried."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.contracts import ACTION_KINDS, ContractError
from app.engine.errors import BlindRetryForbidden
from app.models import Action, ActionStatus

_RETRY_FLAG = "proven_unsent"


def reserve_action(
    session: Session,
    *,
    case_id: UUID,
    kind: str,
    idem_key: str,
    request: dict[str, Any] | None = None,
) -> Action:
    """Create a pending action, or return the one already reserved for this key."""
    if kind not in ACTION_KINDS:
        raise ContractError("Unknown action kind")
    if not idem_key:
        raise ContractError("Action idempotency key is required")
    existing = session.scalar(select(Action).where(Action.idem_key == idem_key))
    if existing is not None:
        return existing
    session.execute(
        pg_insert(Action)
        .values(
            id=uuid4(),
            case_id=case_id,
            kind=kind,
            idem_key=idem_key,
            status=ActionStatus.pending,
            request=dict(request or {}),
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_actions_idem_key")
    )
    session.flush()
    winner = session.scalar(select(Action).where(Action.idem_key == idem_key))
    if winner is None:
        raise ContractError("Action was not stored")
    return winner


def _require(action: Action, status: ActionStatus) -> None:
    if action.status is not status:
        raise BlindRetryForbidden()


def record_sent(action: Action, external_id: str) -> None:
    """The provider accepted the call and returned an id."""
    if action.status is ActionStatus.uncertain:
        raise BlindRetryForbidden()
    _require(action, ActionStatus.pending)
    action.status = ActionStatus.sent
    action.external_id = external_id
    action.attempts += 1
    request = dict(action.request or {})
    request.pop(_RETRY_FLAG, None)
    action.request = request


def record_uncertain(action: Action) -> None:
    """The call may have landed. Do not send it again from this state."""
    _require(action, ActionStatus.pending)
    action.status = ActionStatus.uncertain
    action.attempts += 1


def record_failed(action: Action) -> None:
    """A definite 4xx-style refusal. The desk shows the failure."""
    if action.status is ActionStatus.uncertain:
        raise BlindRetryForbidden()
    _require(action, ActionStatus.pending)
    action.status = ActionStatus.failed
    action.attempts += 1


def reconcile_action(action: Action, *, found: bool, search_completed: bool) -> str:
    """Found in Sent becomes reconciled. Proven absent may return to pending once."""
    _require(action, ActionStatus.uncertain)
    if found:
        action.status = ActionStatus.reconciled
        return "reconciled"
    if not search_completed:
        return "uncertain"
    if action.attempts < 2:
        action.status = ActionStatus.pending
        request = dict(action.request or {})
        request[_RETRY_FLAG] = True
        action.request = request
        return "retry_once"
    return "uncertain"


def retry_uncertain(action: Action) -> None:
    """Refuse to send while the action is still uncertain or the search did not clear it."""
    if action.status is ActionStatus.uncertain:
        raise BlindRetryForbidden()
    if action.status is not ActionStatus.pending or not (action.request or {}).get(_RETRY_FLAG):
        raise BlindRetryForbidden()
