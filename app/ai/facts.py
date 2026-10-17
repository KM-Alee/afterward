"""Read-only case facts and a proposal sink for the family agent's tools. Nothing approves."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.status import classify_account, finish_summary, four_dimensions
from app.models import Account, Case, Decision, DecisionStatus


def make_case_facts(
    session_factory: Callable[[], Session],
) -> Callable[[str], dict[str, object]]:
    """Facts for `get_case_status`: counts and per-account dimensions computed by code."""

    def facts(case_ref: str) -> dict[str, object]:
        with session_factory() as session:
            case = session.scalar(select(Case).where(Case.ref == case_ref))
            if case is None:
                return {"found": False}
            accounts = list(session.scalars(select(Account).where(Account.case_id == case.id)))
            summary = finish_summary([(item, True) for item in accounts])
            return {
                "found": True,
                "summary": summary.text,
                "accounts": [
                    {
                        "account_ref": item.account_ref,
                        "label": item.service_label,
                        "bucket": classify_account(item),
                    }
                    for item in accounts
                ],
            }

    return facts


def make_account_facts(
    session_factory: Callable[[], Session], case_ref: str
) -> Callable[[str], dict[str, object]]:
    """Facts for `get_account`, limited to one case."""

    def facts(account_ref: str) -> dict[str, object]:
        with session_factory() as session:
            row = session.scalar(
                select(Account)
                .join(Case, Case.id == Account.case_id)
                .where(Case.ref == case_ref, Account.account_ref == account_ref)
            )
            if row is None:
                return {"found": False}
            return {"found": True, "ownership": row.ownership.value, **four_dimensions(row)}

    return facts


def make_proposal_sink(
    session_factory: Callable[[], Session], case_ref: str
) -> Callable[[str, dict[str, object]], None]:
    """Write a proposal as an `open` decision with no options. The family still chooses."""

    def sink(kind: str, payload: dict[str, object]) -> None:
        with session_factory() as session:
            case = session.scalar(select(Case).where(Case.ref == case_ref))
            if case is None:
                raise LookupError("unknown case")
            session.add(
                Decision(
                    case_id=case.id,
                    kind=f"proposed_{kind}",
                    payload=dict(payload),
                    options=[],
                    status=DecisionStatus.open,
                )
            )
            session.commit()

    return sink
