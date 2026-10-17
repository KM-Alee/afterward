"""Database-backed pieces of the live Telegram conversation.

Building the conversation from the case rows, remembering it across restarts, deduplicating
channel updates, attaching the connected inbox and queueing an approved send. Every function
takes a Session, so tests run them on real Postgres without a server.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.conversation.dependency import ProviderFacts
from app.conversation.session import Conversation, Invite
from app.discovery.agent import AgentRunner
from app.discovery.directory import lookup
from app.discovery.household import HouseholdScan
from app.models import (
    Account,
    Case,
    ConversationSnapshot,
    MailConnection,
    Member,
    MemberRole,
    ProcessedUpdate,
    ProviderProfile,
)

logger = logging.getLogger(__name__)

CHANNEL = "telegram"
CONNECT_PATH = "/family/onboarding"  # the page with the connect forms; start is POST-only


def doc_labels(required_docs: list[Any]) -> tuple[str, ...]:
    """'death_certificate' + 'photo' -> 'death certificate (photo)'."""
    labels: list[str] = []
    for row in required_docs:
        if not isinstance(row, dict) or not row.get("type"):
            continue
        label = str(row["type"]).replace("_", " ")
        if row.get("form"):
            label += f" ({str(row['form']).replace('_', ' ')})"
        labels.append(label)
    return tuple(labels)


def provider_facts(session: Session, case_id: UUID) -> dict[str, ProviderFacts]:
    """Declared facts per provider with an account in the case. The recipient is profile data."""
    from app.conversation.demo_malik import PROVIDERS as DEMO

    rows = session.execute(
        select(Account, ProviderProfile)
        .join(ProviderProfile, ProviderProfile.id == Account.provider_id)
        .where(Account.case_id == case_id)
        .order_by(Account.created_at)
    ).all()
    found: dict[str, ProviderFacts] = {}
    for account, profile in rows:
        if profile.name in found or not profile.approved_recipients:
            continue
        demo = DEMO.get(profile.name)
        found[profile.name] = ProviderFacts(
            name=profile.name,
            short=profile.name.split()[0],
            recipient=str(profile.approved_recipients[0]),
            documents=doc_labels(list(profile.required_docs or [])),
            account_ref=account.account_ref,
            account_label=account.service_label,
            consequence=demo.consequence if demo is not None else "",
        )
    return found


def allowed_recipients(session: Session, case_id: UUID) -> tuple[str, ...]:
    seen: list[str] = []
    rows = session.scalars(
        select(ProviderProfile)
        .join(Account, Account.provider_id == ProviderProfile.id)
        .where(Account.case_id == case_id)
    ).all()
    for profile in rows:
        for address in profile.approved_recipients or []:
            if str(address) not in seen:
                seen.append(str(address))
    return tuple(seen)


def pick_line(facts: dict[str, ProviderFacts]) -> ProviderFacts | None:
    """The flagged shared line: a mobile, broadband or landline account with known facts."""
    for item in facts.values():
        entry = lookup(item.name)
        if entry is not None and entry.category in {"mobile", "broadband", "landline"}:
            return item
    return next(iter(facts.values()), None)


def owner_sender_for(session: Session, case_id: UUID, member_id: UUID | None) -> str:
    """Telegram id of the member who connected an inbox, else the case owner, else empty."""
    if member_id is not None:
        member = session.get(Member, member_id)
        if member is not None and member.channel_user_id:
            return member.channel_user_id
    owner = session.scalar(
        select(Member).where(
            Member.case_id == case_id,
            Member.role == MemberRole.owner,
            Member.channel_user_id.is_not(None),
        )
    )
    return owner.channel_user_id or "" if owner is not None else ""


def active_connection(session: Session, case_id: UUID) -> MailConnection | None:
    return session.scalar(
        select(MailConnection)
        .where(MailConnection.case_id == case_id, MailConnection.revoked_at.is_(None))
        .order_by(MailConnection.created_at.desc())
        .limit(1)
    )


def _mailbox(settings: Any, connection: MailConnection) -> Any:
    from app.integrations.connect import mailbox_for_connection

    params = inspect.signature(mailbox_for_connection).parameters
    if "settings" in params:
        return mailbox_for_connection(settings, connection)
    return mailbox_for_connection(connection)  # pragma: no cover


def build_scan(
    session: Session,
    settings: Any,
    case: Case,
    *,
    mailbox_factory: Callable[[Any, MailConnection], Any] | None = None,
) -> tuple[HouseholdScan, UUID] | None:
    """A scan for the case's active connection, or None. Never raises for a bad token."""
    connection = active_connection(session, case.id)
    if connection is None:
        return None
    try:
        client = (mailbox_factory or _mailbox)(settings, connection)
        scan = HouseholdScan(
            client=client,
            mailbox=connection.address,
            owner=owner_sender_for(session, case.id, connection.connected_by_member_id),
            names=(case.deceased_name,),
            account_of=connection.account_of,
            stated_authority=connection.stated_authority,
        )
    except Exception:
        logger.info("scan build", extra={"kind": "discovery.scan", "ok": False})
        return None
    return scan, connection.id


def connect_url(settings: Any) -> str | None:
    base = str(getattr(settings, "public_base_url", "") or "").rstrip("/")
    return f"{base}{CONNECT_PATH}" if base else None


def build_conversation(
    session: Session,
    settings: Any,
    ai: Any,
    *,
    case_id: UUID,
    runner: AgentRunner | None,
    mailbox_factory: Callable[[Any, MailConnection], Any] | None = None,
) -> Conversation | None:
    """A conversation from the case rows, with saved state restored. None for an unknown case."""
    from app.conversation.demo_malik import INVITE_TOKEN, NORTHLINE

    case = session.get(Case, case_id)
    if case is None:
        return None
    facts = provider_facts(session, case_id)
    line = pick_line(facts) or NORTHLINE
    invites: dict[str, Invite] = {}
    if case.is_demo:
        invites[INVITE_TOKEN] = Invite(
            token=INVITE_TOKEN, name="Amina Malik", stated_role="his wife; lives in the family home"
        )
    built = build_scan(session, settings, case, mailbox_factory=mailbox_factory)
    conversation = Conversation(
        ai,
        providers=facts or {NORTHLINE.name: NORTHLINE},
        allowed_recipients=allowed_recipients(session, case_id) or (NORTHLINE.recipient,),
        line=line,
        invites=invites,
        case_date=case.date_of_death if isinstance(case.date_of_death, date) else None,
        scan=built[0] if built else None,
        discovery_runner=runner,
        discovery=True,
        connect_url=connect_url(settings),
    )
    conversation.case_id = case_id
    conversation.scan_connection_id = built[1] if built else None
    saved = session.get(ConversationSnapshot, case_id)
    if saved is not None and saved.state:
        conversation.load_state(saved.state)
    elif case.deceased_name:
        conversation.state.deceased_name = case.deceased_name
    return conversation


def refresh_scan(
    session: Session,
    settings: Any,
    conversation: Conversation,
    *,
    mailbox_factory: Callable[[Any, MailConnection], Any] | None = None,
) -> None:
    """Pick up an inbox connected (or revoked) on the web since the last turn."""
    case_id = getattr(conversation, "case_id", None)
    if case_id is None:
        return
    current = active_connection(session, case_id)
    if current is None:
        conversation.scan = None
        conversation.scan_connection_id = None
        return
    if conversation.scan is not None and conversation.scan_connection_id == current.id:
        return
    case = session.get(Case, case_id)
    if case is None:
        return
    built = build_scan(session, settings, case, mailbox_factory=mailbox_factory)
    if built is not None:
        conversation.scan, conversation.scan_connection_id = built
        conversation.discovery = True


def save_state(session: Session, conversation: Conversation) -> bool:
    """Upsert the conversation snapshot. False when the conversation has no case."""
    case_id = getattr(conversation, "case_id", None)
    if case_id is None:
        return False
    state = conversation.export_state()
    row = session.get(ConversationSnapshot, case_id)
    if row is None:
        session.add(ConversationSnapshot(case_id=case_id, state=state))
    else:
        row.state = state
        row.updated_at = datetime.now(UTC)
    session.flush()
    return True


def claim_update(session: Session, update_id: int | str, channel: str = CHANNEL) -> bool:
    """True the first time an update id is seen, False for a retry."""
    result = session.execute(
        pg_insert(ProcessedUpdate)
        .values(channel=channel, update_id=str(update_id))
        .on_conflict_do_nothing(constraint="uq_processed_updates_channel_update")
        .returning(ProcessedUpdate.id)
    )
    return result.scalar() is not None


def latest_case_id(session: Session) -> UUID | None:
    return session.scalar(select(Case.id).order_by(Case.created_at.desc()).limit(1))


def enqueue_send(session: Session, conversation: Conversation, sender: str) -> str | None:
    """Queue the approved request as a send_request job. Returns the job id, or None.

    None means the approval could not be bound to rows (no case, no account, no member,
    stale plan); the caller must then send nothing.
    """
    from app.engine.dependencies import apply_dependency
    from app.engine.errors import AlreadyDecided, DependencyRequired, StalePlan
    from app.engine.jobs import enqueue
    from app.engine.plans import approve, latest_plan, revise_plan
    from app.models import PlanAction

    case_id = getattr(conversation, "case_id", None)
    state = conversation.state
    plan = state.plan
    if case_id is None or plan is None or state.approval is None:
        return None
    item = next((row for row in plan.items if row.action == "transfer"), None)
    if item is None or item.recipient not in conversation.allowed_recipients:
        return None
    account = session.scalar(
        select(Account).where(Account.case_id == case_id, Account.account_ref == item.account_ref)
    )
    member = session.scalar(
        select(Member).where(Member.case_id == case_id, Member.channel_user_id == sender)
    )
    if account is None or member is None or member.role is not MemberRole.owner:
        return None
    try:
        if conversation.last_dependency is not None:
            from app.ai.schemas import DependencyOut

            apply_dependency(
                session,
                case_id=case_id,
                account=account,
                dependency=DependencyOut.model_validate(conversation.last_dependency),
                source_member_id=None,
                plan=None,
            )
        revised = revise_plan(
            session,
            case_id=case_id,
            account_id=account.id,
            action=PlanAction.transfer,
            conditions=[{"key": key, "type": "bool", "value": "true"} for key in item.conditions],
            documents=[{"type": label} for label in item.documents],
            recipient=item.recipient,
            fallback=item.fallback,
        )
        approval = approve(
            session,
            plan_id=revised.id,
            version=revised.version,
            plan_hash_value=revised.hash,
            member_id=member.id,
            card={"text": state.approval.text()},
        )
        latest = latest_plan(session, account.id)
        if latest is None or latest.id != revised.id:
            return None
        job = enqueue(
            session,
            case_id=case_id,
            kind="send_request",
            run_at_case_time=datetime.now(UTC),
            idem_key=f"send:{revised.id}:{revised.version}",
            payload={
                "plan_id": str(revised.id),
                "plan_version": revised.version,
                "plan_hash": revised.hash,
                "approval_id": str(approval.id),
                "action": "transfer",
                "outbound": True,
                "reason": {"type": "always"},
            },
        )
    except (StalePlan, AlreadyDecided, DependencyRequired):
        return None
    return str(job.id)
