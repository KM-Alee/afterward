"""Match a reply to a case and account, then record the recipient check.

Order is thread, then an exact From or Reply-To address, then a plus-tag on
the same domain as an approved recipient. Email text cannot add a recipient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import MailMessage
from app.models import Account, Action, Message, MessageDirection, ProviderProfile, RecipientCheck

MatchMethod = Literal["thread", "address", "plus_tag", "none"]


@dataclass(frozen=True)
class MatchResult:
    """Where a message landed. `unsorted` means no single account was found."""

    case_id: UUID | None
    account_id: UUID | None
    provider_id: UUID | None
    recipient_check: RecipientCheck
    method: MatchMethod
    unsorted: bool


def bare_address(value: str | None) -> str:
    """Lower-case the mailbox address and drop a display name."""
    from app.mail.parse import split_mailbox

    if not value:
        return ""
    _name, address = split_mailbox(value)
    return (address or value).strip().casefold()


def match_message(
    session: Session,
    message: MailMessage,
    *,
    bound_case_id: UUID | None = None,
) -> MatchResult:
    """Match one decoded message. Unmatched mail stays unsorted."""
    profiles = list(session.scalars(select(ProviderProfile)))
    thread = _match_thread(session, message.thread_id)
    provider_id: UUID | None = None
    account_id: UUID | None = None
    case_id = bound_case_id
    method: MatchMethod = "none"
    if thread is not None:
        case_id, account_id, provider_id = thread
        method = "thread"
    else:
        addressed = _match_address(session, message, profiles, bound_case_id)
        if addressed is not None:
            case_id, account_id, provider_id = addressed
            method = "address"
        else:
            tagged = _match_plus(session, message, profiles, bound_case_id)
            if tagged is not None:
                case_id, account_id, provider_id = tagged
                method = "plus_tag"
    approved = _approved_for(profiles, provider_id, case_id, session)
    check = recipient_check(message.from_addr, message.reply_to, approved)
    unsorted = account_id is None
    return MatchResult(
        case_id=case_id,
        account_id=account_id,
        provider_id=provider_id,
        recipient_check=check,
        method=method,
        unsorted=unsorted,
    )


def recipient_check(
    from_addr: str,
    reply_to: str | None,
    approved: set[str],
) -> RecipientCheck:
    """Approve only an exact approved From whose Reply-To does not point elsewhere."""
    sender = bare_address(from_addr)
    reply = bare_address(reply_to)
    sender_ok = sender in approved
    reply_ok = not reply or reply == sender or reply in approved
    if sender_ok and reply_ok:
        return RecipientCheck.approved
    if sender_ok and not reply_ok:
        return RecipientCheck.reply_to_mismatch
    if reply and reply in approved and not sender_ok:
        return RecipientCheck.reply_to_mismatch
    return RecipientCheck.unapproved


def list_unsorted(session: Session, case_id: UUID) -> list[Message]:
    """Inbound rows on this case that still do not match one account."""
    rows = list(
        session.scalars(
            select(Message).where(
                Message.case_id == case_id,
                Message.direction == MessageDirection.inbound,
            )
        )
    )
    unsorted: list[Message] = []
    for row in rows:
        if match_message(session, _message_view(row), bound_case_id=case_id).unsorted:
            unsorted.append(row)
    return unsorted


def _message_view(row: Message) -> MailMessage:
    from datetime import UTC, datetime

    return MailMessage(
        mailbox="",
        gmail_id=row.gmail_id or "",
        thread_id=row.thread_id or "",
        rfc_message_id=row.rfc_message_id or "",
        from_addr=row.from_addr,
        reply_to=row.reply_to,
        to_addrs=list(row.to_addrs or []),
        subject=row.subject,
        latest_text=row.latest_text,
        full_text=row.latest_text,
        received_at=row.received_at or datetime.now(UTC),
    )


def _match_thread(session: Session, thread_id: str) -> tuple[UUID, UUID | None, UUID | None] | None:
    if not thread_id:
        return None
    outbound = session.scalar(
        select(Message).where(
            Message.thread_id == thread_id,
            Message.direction == MessageDirection.outbound,
        )
    )
    if outbound is None:
        return None
    account_id: UUID | None = None
    provider_id: UUID | None = None
    actions = session.scalars(select(Action).where(Action.case_id == outbound.case_id))
    for action in actions:
        request = action.request or {}
        if request.get("thread_id") != thread_id:
            continue
        raw = request.get("account_id")
        if not raw:
            continue
        account_id = UUID(str(raw))
        account = session.get(Account, account_id)
        if account is not None:
            provider_id = account.provider_id
        break
    return outbound.case_id, account_id, provider_id


def _match_address(
    session: Session,
    message: MailMessage,
    profiles: list[ProviderProfile],
    bound_case_id: UUID | None,
) -> tuple[UUID | None, UUID | None, UUID | None] | None:
    index = _address_index(profiles)
    profile = index.get(bare_address(message.from_addr))
    if profile is None:
        profile = index.get(bare_address(message.reply_to))
    if profile is None:
        return None
    return _place(session, profile, bound_case_id)


def _match_plus(
    session: Session,
    message: MailMessage,
    profiles: list[ProviderProfile],
    bound_case_id: UUID | None,
) -> tuple[UUID | None, UUID | None, UUID | None] | None:
    wanted = _plus_parts(_candidate_addresses(message))
    if not wanted:
        return None
    for profile in profiles:
        known = _plus_parts([str(item) for item in profile.approved_recipients])
        if wanted & known:
            return _place(session, profile, bound_case_id)
    return None


def _place(
    session: Session, profile: ProviderProfile, bound_case_id: UUID | None
) -> tuple[UUID | None, UUID | None, UUID | None]:
    statement = select(Account).where(Account.provider_id == profile.id)
    if bound_case_id is not None:
        statement = statement.where(Account.case_id == bound_case_id)
    accounts = list(session.scalars(statement))
    if len(accounts) == 1:
        return accounts[0].case_id, accounts[0].id, profile.id
    case_id = bound_case_id
    if case_id is None and accounts:
        case_ids = {account.case_id for account in accounts}
        if len(case_ids) == 1:
            case_id = accounts[0].case_id
    return case_id, None, profile.id


def _approved_for(
    profiles: list[ProviderProfile],
    provider_id: UUID | None,
    case_id: UUID | None,
    session: Session,
) -> set[str]:
    if provider_id is not None:
        chosen = [profile for profile in profiles if profile.id == provider_id]
    elif case_id is not None:
        linked = set(
            session.scalars(
                select(Account.provider_id).where(
                    Account.case_id == case_id,
                    Account.provider_id.is_not(None),
                )
            )
        )
        chosen = [profile for profile in profiles if profile.id in linked]
    else:
        chosen = profiles
    approved: set[str] = set()
    for profile in chosen:
        for item in profile.approved_recipients:
            address = bare_address(str(item))
            if address:
                approved.add(address)
    return approved


def _address_index(profiles: list[ProviderProfile]) -> dict[str, ProviderProfile]:
    index: dict[str, ProviderProfile] = {}
    for profile in profiles:
        for item in profile.approved_recipients:
            address = bare_address(str(item))
            if address:
                index[address] = profile
    return index


def _candidate_addresses(message: MailMessage) -> list[str]:
    values = [message.from_addr, message.reply_to or "", *message.to_addrs]
    return [value for value in values if value]


def _plus_parts(addresses: list[str]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for value in addresses:
        address = bare_address(value)
        if "@" not in address:
            continue
        local, domain = address.split("@", 1)
        if "+" not in local:
            continue
        _base, tag = local.split("+", 1)
        if tag:
            found.add((tag, domain))
    return found
