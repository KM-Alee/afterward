"""Versioned plans. The hash covers action, conditions, documents and recipient."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.engine.errors import AlreadyDecided, DependencyRequired, StalePlan
from app.models import Approval, ApprovalStatus, Dependency, Plan, PlanAction, PlanStatus

_HASH_FIELDS = ("action", "conditions", "documents", "recipient")


def plan_hash(
    action: PlanAction | str,
    conditions: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    recipient: str,
) -> str:
    """Stable hash. Key order and condition order do not change it."""
    action_value = action.value if isinstance(action, PlanAction) else str(action)
    payload = {
        "action": action_value,
        "conditions": sorted(conditions, key=lambda item: json.dumps(item, sort_keys=True)),
        "documents": sorted(documents, key=lambda item: json.dumps(item, sort_keys=True)),
        "recipient": recipient,
    }
    if set(payload) != set(_HASH_FIELDS):
        raise RuntimeError("plan hash fields drifted")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def latest_plan(session: Session, account_id: UUID) -> Plan | None:
    """The highest version for an account. Superseded rows stay for the audit trail."""
    return session.scalar(
        select(Plan).where(Plan.account_id == account_id).order_by(Plan.version.desc()).limit(1)
    )


def _void_previous(session: Session, account_id: UUID) -> None:
    plan_ids = select(Plan.id).where(Plan.account_id == account_id)
    session.execute(
        update(Approval)
        .where(
            Approval.plan_id.in_(plan_ids),
            Approval.status.in_((ApprovalStatus.open, ApprovalStatus.approved)),
        )
        .values(status=ApprovalStatus.void)
    )


def revise_plan(
    session: Session,
    *,
    case_id: UUID,
    account_id: UUID,
    action: PlanAction | str,
    conditions: list[dict[str, Any]],
    documents: list[dict[str, Any]] | None = None,
    recipient: str,
    fallback: str = "",
) -> Plan:
    """Insert the next version when the hashed content changes and void earlier approvals."""
    action_value = action if isinstance(action, PlanAction) else PlanAction(action)
    documents = list(documents or [])
    digest = plan_hash(action_value, conditions, documents, recipient)
    current = latest_plan(session, account_id)
    if current is not None and current.hash == digest and current.action == action_value:
        return current
    version = 1 if current is None else current.version + 1
    if current is not None:
        current.status = PlanStatus.superseded
        _void_previous(session, account_id)
    plan = Plan(
        case_id=case_id,
        account_id=account_id,
        version=version,
        action=action_value,
        conditions=conditions,
        documents_to_disclose=documents,
        recipient=recipient,
        fallback=fallback,
        status=PlanStatus.pending_approval,
        hash=digest,
    )
    session.add(plan)
    session.flush()
    return plan


def approve(
    session: Session,
    *,
    plan_id: UUID,
    version: int,
    plan_hash_value: str,
    member_id: UUID,
    card: dict[str, Any] | None = None,
) -> Approval:
    """Compare-and-set on plan id, version and hash. A mismatch is a 409 stale error."""
    plan = session.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None or plan.version != version or plan.hash != plan_hash_value:
        raise StalePlan()
    if plan.status is PlanStatus.superseded:
        raise StalePlan()
    current = latest_plan(session, plan.account_id)
    if current is None or current.id != plan.id:
        raise StalePlan()
    if plan.action in {PlanAction.close, PlanAction.transfer}:
        dependency = session.scalar(
            select(Dependency.id).where(Dependency.account_id == plan.account_id).limit(1)
        )
        if dependency is None:
            raise DependencyRequired()
    existing = session.scalar(
        select(Approval.id).where(
            Approval.plan_id == plan.id,
            Approval.status == ApprovalStatus.approved,
        )
    )
    if existing is not None:
        raise AlreadyDecided()
    approval = Approval(
        case_id=plan.case_id,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_hash=plan.hash,
        member_id=member_id,
        card=card or {},
        status=ApprovalStatus.approved,
    )
    plan.status = PlanStatus.approved
    session.add(approval)
    session.flush()
    return approval


def acceptance_allowed(session: Session, approval_id: UUID) -> bool:
    """Spoken acceptance is refused when the bound approval was voided or the hash moved."""
    approval = session.get(Approval, approval_id)
    if approval is None or approval.status is not ApprovalStatus.approved:
        return False
    plan = session.get(Plan, approval.plan_id)
    if plan is None or plan.hash != approval.plan_hash or plan.version != approval.plan_version:
        return False
    current = latest_plan(session, plan.account_id)
    return current is not None and current.id == plan.id and current.hash == approval.plan_hash
