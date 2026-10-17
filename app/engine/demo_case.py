"""Idempotent Malik demo case in the database, so the desk and the runner share real rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demo.seed import DEMO_CASE_REF, seed_malik
from app.engine.jobs import enqueue
from app.engine.plans import approve, revise_plan
from app.models import (
    Account,
    Case,
    Dependency,
    DependencyKind,
    DocsStatus,
    Job,
    Member,
    MemberRole,
    MoneyStatus,
    PlanAction,
    ServiceStatus,
)

FOLLOWUP_DAYS = 14
FOLLOWUP_REF = "FL-5531"

# Dimensions the demo desk shows for each reference, as in the approved board.
_OVERLAY: dict[str, tuple[ServiceStatus, MoneyStatus, DocsStatus]] = {
    "4417": (ServiceStatus.requested, MoneyStatus.none, DocsStatus.sent),
    "CP-77120": (ServiceStatus.requested, MoneyStatus.needs_review, DocsStatus.none_needed),
    "SB-88213": (ServiceStatus.requested, MoneyStatus.none, DocsStatus.none_needed),
    "FL-5531": (ServiceStatus.acknowledged, MoneyStatus.none, DocsStatus.sent),
}


def ensure_demo_case(session: Session, *, providers_mailbox: str = "") -> UUID:
    """Return the demo case id, inserting the case, members, accounts and follow-up once."""
    case = session.scalar(select(Case).where(Case.ref == DEMO_CASE_REF))
    if case is None:
        case = seed_malik(session, providers_mailbox=providers_mailbox)
        accounts = {
            a.account_ref: a
            for a in session.scalars(select(Account).where(Account.case_id == case.id))
        }
        for ref, (service, money, docs) in _OVERLAY.items():
            account = accounts[ref]
            account.status_service, account.status_money, account.status_docs = service, money, docs
            account.next_step = {"owner": "provider", "action": "Wait for the reply"}
        owner = session.scalar(
            select(Member).where(Member.case_id == case.id, Member.role == MemberRole.owner)
        )
        if owner is not None:
            owner.consent = {"status": "granted", "demo": True}
        session.flush()
    _name_and_track(session, case)
    _ensure_followup(session, case)
    return case.id


# Demo organisations that have no provider profile yet: name them, never guess an address.
_DEMO_NAMES = {"HW-20418": "Harbor Water", "ML-6610": "Meridian Life", "PB-3017": "Paperleaf Books"}


def _name_and_track(session: Session, case: Case) -> None:
    """Give every demo account a provider name and a track from the directory (idempotent)."""
    from app.discovery.directory import track_for
    from app.models import ProviderProfile

    for account in session.scalars(select(Account).where(Account.case_id == case.id)):
        step = dict(account.next_step or {})
        name = ""
        if account.provider_id is not None:
            profile = session.get(ProviderProfile, account.provider_id)
            name = profile.name if profile is not None else ""
        if not name:
            name = str(step.get("provider") or _DEMO_NAMES.get(account.account_ref, ""))
            if name and step.get("provider") != name:
                step["provider"] = name
                account.next_step = step
        if not account.track:
            account.track = track_for(name or account.service_label)
    session.flush()


def _ensure_followup(session: Session, case: Case) -> None:
    """A FitLife follow-up due 14 days of case time from now, bound to an approved plan."""
    key = f"followup:demo:{case.id}:{FOLLOWUP_REF}"
    if session.scalar(select(Job.id).where(Job.idem_key == key)) is not None:
        return
    account = session.scalar(
        select(Account).where(Account.case_id == case.id, Account.account_ref == FOLLOWUP_REF)
    )
    owner = session.scalar(
        select(Member).where(Member.case_id == case.id, Member.role == MemberRole.owner)
    )
    if account is None or owner is None:
        return
    session.add(
        Dependency(
            case_id=case.id,
            account_id=account.id,
            kind=DependencyKind.access,
            statement="Demo seed: nobody else uses this membership.",
            source_member_id=owner.id,
        )
    )
    plan = revise_plan(
        session,
        case_id=case.id,
        account_id=account.id,
        action=PlanAction.close,
        conditions=[{"key": "no_new_contract", "value": True}],
        documents=[{"type": "death_certificate", "form": "photo"}],
        recipient="members@fitlife.example",
        fallback="Ask the family before anything else is sent.",
    )
    approval = approve(
        session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=owner.id,
        card={"demo": True},
    )
    sent_at = datetime.now(UTC)
    enqueue(
        session,
        case_id=case.id,
        kind="followup",
        run_at_case_time=sent_at + timedelta(days=FOLLOWUP_DAYS),
        idem_key=key,
        payload={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "plan_hash": plan.hash,
            "approval_id": str(approval.id),
            "outbound": True,
            "reason": {
                "type": "awaiting_reply",
                "account_id": str(account.id),
                "since": sent_at.isoformat(),
            },
        },
    )
    session.flush()
