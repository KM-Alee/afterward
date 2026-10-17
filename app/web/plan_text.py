"""The approved plan's request text for the call room, read from Plan and Approval rows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.models import Account
from app.story import approved_plan_for, condition_label
from app.web.projection import resolve_case

logger = logging.getLogger(__name__)
CALL_ACCOUNT_REF = "4417"


def request_text_for(session_factory: Callable[[], Any], case_id: Any, ref: str) -> str | None:
    """Request wording for one account, only if its plan has a current approval."""
    with session_factory() as session:
        case = resolve_case(session, case_id)
        if case is None:
            return None
        account = session.scalar(
            select(Account).where(Account.case_id == case.id, Account.account_ref == ref)
        )
        if account is None:
            return None
        found = approved_plan_for(session, account.id)
        if found is None:
            return None
        plan, _approval = found
        conditions = "; ".join(condition_label(str(c.get("key"))).lower() for c in plan.conditions)
        text = f"{plan.action.value.replace('_', ' ').capitalize()}: {account.service_label}."
        return f"{text} Conditions: {conditions}." if conditions else text


def attach_request_provider(surface: Any, room: Any, case_id: Any) -> None:
    """Point a call room at the approved plan. With no database it reports no plan."""

    def provider() -> str | None:
        factory = getattr(surface, "session_factory", None)
        if factory is None:
            return None
        try:
            return request_text_for(factory, case_id, CALL_ACCOUNT_REF)
        except Exception:
            logger.info("call plan text", extra={"kind": "call.plan", "ok": False})
            return None

    room.request_provider = provider
