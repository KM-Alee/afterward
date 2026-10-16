"""Dependency answers become plan conditions in code. The model does not write the checks."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import DependencyOut
from app.engine.plans import revise_plan
from app.models import Account, Dependency, DependencyKind, Plan


@dataclass(frozen=True)
class DependencyEffect:
    """Conditions to add, and the other account an access answer links."""

    conditions: tuple[dict[str, str], ...]
    link_account_ref: str | None


def effect_for(dependency: DependencyOut) -> DependencyEffect:
    """Memory keeps voicemail. Access keeps the number and links the dependent account."""
    if dependency.kind == "memory":
        return DependencyEffect(
            ({"key": "voicemail_preserved", "type": "bool", "value": "true"},),
            None,
        )
    if dependency.kind == "access":
        return DependencyEffect(
            ({"key": "number_kept", "type": "bool", "value": "true"},),
            dependency.linked_number or dependency.linked_provider,
        )
    if dependency.kind == "shared_service":
        return DependencyEffect(
            ({"key": "number_kept", "type": "bool", "value": "true"},),
            dependency.linked_number,
        )
    return DependencyEffect(
        ({"key": "document_required", "type": "enum", "value": "retain"},),
        None,
    )


def _merge_conditions(
    existing: list[dict[str, object]],
    added: tuple[dict[str, str], ...],
) -> list[dict[str, object]]:
    merged = [dict(item) for item in existing]
    seen = {str(item.get("key")) for item in merged}
    for condition in added:
        if condition["key"] not in seen:
            merged.append(dict(condition))
            seen.add(condition["key"])
    return merged


def apply_dependency(
    session: Session,
    *,
    case_id: UUID,
    account: Account,
    dependency: DependencyOut,
    source_member_id: UUID | None,
    plan: Plan | None,
) -> tuple[Dependency, Plan | None]:
    """Store the answer, link an access dependency, and revise the plan when one exists."""
    effect = effect_for(dependency)
    linked_id: UUID | None = None
    if effect.link_account_ref:
        linked = session.scalar(
            select(Account).where(
                Account.case_id == case_id,
                Account.account_ref == effect.link_account_ref,
            )
        )
        if linked is not None:
            linked_id = linked.id
    row = Dependency(
        case_id=case_id,
        account_id=account.id,
        kind=DependencyKind(dependency.kind),
        statement=dependency.statement,
        source_member_id=source_member_id,
        linked_account_id=linked_id,
    )
    session.add(row)
    session.flush()
    revised = plan
    if plan is not None:
        conditions = _merge_conditions(list(plan.conditions or []), effect.conditions)
        revised = revise_plan(
            session,
            case_id=case_id,
            account_id=account.id,
            action=plan.action,
            conditions=conditions,  # type: ignore[arg-type]
            documents=list(plan.documents_to_disclose or []),
            recipient=plan.recipient,
            fallback=plan.fallback,
        )
    return row, revised
