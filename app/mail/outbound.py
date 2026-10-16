"""Send, follow up, hand off and reconcile outbound effects through action records.

The visible footer is added here. The mailbox only checks that the marker is present.
Web-form and phone-only providers become a `handoff` action and are not emailed.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.contracts import EventBus, Mailbox, SendRequest
from app.mail.calendar import CalendarTransport, calendar_body
from app.mail.errors import DeliveryUncertain, MailError
from app.mail.parse import extract_text
from app.models import (
    Account,
    Action,
    ActionStatus,
    Case,
    CaseControl,
    Member,
    MemberRole,
    Message,
    MessageDirection,
    ProviderProfile,
)

DISCLOSURE = "Prepared by Afterward, an AI assistant, on behalf of {owner} (as stated)."
FOLLOWUP_BODY = (
    "I am following up on the earlier request. Please reply with the outcome in writing."
)


def compose_outbound(
    body: str, *, owner_name: str, case_ref: str, action_key: str
) -> tuple[str, str]:
    """Append the disclosure and the visible `Ref AW-…` marker. Returns text and footer ref."""
    footer_ref = visible_ref(case_ref, action_key)
    text = f"{body.rstrip()}\n\n{DISCLOSURE.format(owner=owner_name)}\n\nRef {footer_ref}"
    return text, footer_ref


def visible_ref(case_ref: str, action_key: str) -> str:
    """Build `AW-<case>-<action>`. Demo refs already start with `AW-`."""
    if case_ref.startswith("AW-"):
        return f"{case_ref}-{action_key}"
    return f"AW-{case_ref}-{action_key}"


def accepts_email(channels: list[object]) -> bool:
    """True when the declared profile accepts email."""
    return any(str(item).casefold() == "email" for item in channels)


async def execute_action(
    session: Session,
    action: Action,
    *,
    mailbox: Mailbox | None = None,
    calendar: CalendarTransport | None = None,
    bus: EventBus | None = None,
) -> Action:
    """Run one action record. Sent and reconciled records are not sent again."""
    if action.status in {ActionStatus.sent, ActionStatus.reconciled, ActionStatus.failed}:
        return action
    if action.kind == "handoff":
        return _complete_handoff(session, action, bus)
    if action.kind == "calendar_insert":
        return await _insert_event(session, action, calendar, bus)
    if action.kind == "email_send":
        return await _send_or_hand_off(session, action, mailbox, bus)
    action.status = ActionStatus.failed
    return action


async def execute_send_request(
    session: Session,
    action: Action,
    *,
    mailbox: Mailbox,
    bus: EventBus | None = None,
) -> Action:
    """Send an approved request, or record a hand-off when email is not accepted."""
    return await execute_action(session, action, mailbox=mailbox, bus=bus)


async def execute_followup(
    session: Session,
    action: Action,
    *,
    mailbox: Mailbox,
    bus: EventBus | None = None,
) -> Action:
    """Send a follow-up in the existing thread, or hand it off for a non-email provider."""
    request = dict(action.request or {})
    if not request.get("body"):
        request["body"] = FOLLOWUP_BODY
    request["followup"] = True
    action.request = request
    flag_modified(action, "request")
    return await execute_action(session, action, mailbox=mailbox, bus=bus)


async def reconcile_action(session: Session, action: Action, mailbox: Mailbox) -> Action:
    """Search Sent for the footer. Retry once, then leave the action uncertain."""
    if action.status == ActionStatus.reconciled:
        return action
    footer_ref = str((action.request or {}).get("footer_ref") or "")
    mailbox_name = str((action.request or {}).get("mailbox") or "")
    if not footer_ref or not mailbox_name:
        action.status = ActionStatus.uncertain
        return action
    found = await mailbox.search_sent(mailbox_name, footer_ref)
    if found is not None:
        action.status = ActionStatus.reconciled
        action.external_id = found.gmail_id
        _remember(action, thread_id=found.thread_id, rfc_message_id=found.rfc_message_id)
        return action
    if action.external_id or action.attempts >= 2:
        action.status = ActionStatus.uncertain
        return action
    return await _send_email(session, action, mailbox, bus=None)


def _complete_handoff(session: Session, action: Action, bus: EventBus | None) -> Action:
    action.status = ActionStatus.sent
    action.attempts += 1
    if bus is not None:
        channel = str((action.request or {}).get("channel") or "handoff")
        bus.publish(
            session,
            action.case_id,
            "handoff_ready",
            {"channel": channel, "action_id": str(action.id)},
            actor="Afterward",
        )
    return action


async def _send_or_hand_off(
    session: Session,
    action: Action,
    mailbox: Mailbox | None,
    bus: EventBus | None,
) -> Action:
    profile = _profile(session, action)
    channels = list(profile.accepted_channels) if profile is not None else ["email"]
    if not accepts_email(channels):
        return _ensure_handoff(session, action, profile, bus)
    if mailbox is None:
        action.status = ActionStatus.failed
        return action
    blocked = _blocked_reason(session, action)
    if blocked is not None:
        _remember(action, blocked=blocked)
        if bus is not None:
            bus.publish(
                session,
                action.case_id,
                "send_blocked",
                {"reason": blocked, "action_id": str(action.id)},
                actor="Afterward",
            )
        return action
    return await _send_email(session, action, mailbox, bus)


def _ensure_handoff(
    session: Session,
    action: Action,
    profile: ProviderProfile | None,
    bus: EventBus | None,
) -> Action:
    channel = _primary_channel(profile)
    provider_name = profile.name if profile is not None else ""
    idem = f"handoff:{action.idem_key}"
    existing = session.scalar(select(Action).where(Action.idem_key == idem))
    if existing is None:
        existing = Action(
            case_id=action.case_id,
            kind="handoff",
            idem_key=idem,
            status=ActionStatus.pending,
            request={
                "account_id": (action.request or {}).get("account_id"),
                "channel": channel,
                "provider": provider_name,
                "source_idem_key": action.idem_key,
            },
        )
        session.add(existing)
        session.flush()
    _complete_handoff(session, existing, bus)
    action.status = ActionStatus.failed
    _remember(action, blocked="channel_not_email", handoff_idem_key=idem)
    return existing


async def _send_email(
    session: Session,
    action: Action,
    mailbox: Mailbox,
    bus: EventBus | None,
) -> Action:
    case = session.get(Case, action.case_id)
    if case is None:
        action.status = ActionStatus.failed
        return action
    request = dict(action.request or {})
    owner = _owner_name(session, case.id)
    key = _action_key(action)
    body = str(request.get("body") or "")
    text, footer_ref = compose_outbound(body, owner_name=owner, case_ref=case.ref, action_key=key)
    mailbox_name = str(request.get("mailbox") or "")
    to_addrs = [str(item) for item in request.get("to_addrs") or []]
    references = [str(item) for item in request.get("references") or []]
    in_reply_to = request.get("in_reply_to")
    if in_reply_to and str(in_reply_to) not in references:
        references.append(str(in_reply_to))
    send = SendRequest(
        mailbox=mailbox_name,
        to_addrs=to_addrs,
        subject=str(request.get("subject") or "Account request"),
        text=text,
        thread_id=request.get("thread_id"),
        in_reply_to=str(in_reply_to) if in_reply_to else None,
        references=references,
        from_name=str(request.get("from_name") or "Afterward"),
        footer_ref=footer_ref,
    )
    action.attempts += 1
    try:
        sent = await mailbox.send(send)
    except DeliveryUncertain:
        action.status = ActionStatus.uncertain
        _remember(action, footer_ref=footer_ref, mailbox=mailbox_name)
        return action
    action.status = ActionStatus.sent
    action.external_id = sent.gmail_id
    _remember(
        action,
        drop_body=True,
        footer_ref=footer_ref,
        mailbox=mailbox_name,
        thread_id=sent.thread_id,
        rfc_message_id=sent.rfc_message_id,
        gmail_id=sent.gmail_id,
    )
    _store_outbound(session, action, sent_text=text, sent=sent, to_addrs=to_addrs)
    if bus is not None:
        bus.publish(
            session,
            action.case_id,
            "mail_sent",
            {"gmail_id": sent.gmail_id, "footer_ref": footer_ref, "action_id": str(action.id)},
            actor="Afterward",
        )
    return action


async def _insert_event(
    session: Session,
    action: Action,
    calendar: CalendarTransport | None,
    bus: EventBus | None,
) -> Action:
    if calendar is None:
        action.status = ActionStatus.failed
        return action
    blocked = _blocked_reason(session, action)
    if blocked is not None:
        _remember(action, blocked=blocked)
        return action
    body = calendar_body(dict(action.request or {}))
    action.attempts += 1
    try:
        event_id = calendar.insert_event(body)
    except DeliveryUncertain:
        action.status = ActionStatus.uncertain
        return action
    except MailError:
        action.status = ActionStatus.failed
        return action
    action.status = ActionStatus.sent
    action.external_id = event_id
    if bus is not None:
        bus.publish(
            session,
            action.case_id,
            "calendar_inserted",
            {"event_id": event_id, "action_id": str(action.id)},
            actor="Afterward",
        )
    return action


def _store_outbound(
    session: Session,
    action: Action,
    *,
    sent_text: str,
    sent: object,
    to_addrs: list[str],
) -> None:
    extracted = extract_text(sent_text)
    gmail_id = str(getattr(sent, "gmail_id", "") or "")
    thread_id = str(getattr(sent, "thread_id", "") or "")
    rfc_message_id = str(getattr(sent, "rfc_message_id", "") or "")
    mailbox_name = str(getattr(sent, "mailbox", "") or "")
    session.add(
        Message(
            case_id=action.case_id,
            direction=MessageDirection.outbound,
            gmail_id=gmail_id or None,
            thread_id=thread_id or None,
            rfc_message_id=rfc_message_id or None,
            from_addr=mailbox_name,
            to_addrs=to_addrs,
            subject=str((action.request or {}).get("subject") or ""),
            latest_text=extracted.latest_text,
            full_text_sha256=extracted.full_sha256,
            received_at=_now(),
        )
    )
    session.flush()


def _remember(action: Action, *, drop_body: bool = False, **fields: object) -> None:
    request = dict(action.request or {})
    for key, value in fields.items():
        if value is not None:
            request[key] = value
    if drop_body:
        request.pop("body", None)
    action.request = request
    flag_modified(action, "request")


def _blocked_reason(session: Session, action: Action) -> str | None:
    case = session.get(Case, action.case_id)
    if case is None:
        return "missing_case"
    if case.control == CaseControl.stopped:
        return "stopped"
    if case.control == CaseControl.hold:
        return "hold"
    if case.monitoring.value == "interrupted":
        return "monitoring_interrupted"
    return None


def _profile(session: Session, action: Action) -> ProviderProfile | None:
    raw = (action.request or {}).get("account_id")
    if not raw:
        return None
    account = session.get(Account, UUID(str(raw)))
    if account is None or account.provider_id is None:
        return None
    return session.get(ProviderProfile, account.provider_id)


def _primary_channel(profile: ProviderProfile | None) -> str:
    if profile is None or not profile.accepted_channels:
        return "handoff"
    return str(profile.accepted_channels[0])


def _owner_name(session: Session, case_id: UUID) -> str:
    owner = session.scalar(
        select(Member).where(Member.case_id == case_id, Member.role == MemberRole.owner)
    )
    if owner is None or not owner.name:
        return "the account owner"
    return owner.name


def _action_key(action: Action) -> str:
    raw = str((action.request or {}).get("action_key") or action.idem_key)
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", raw)
    return cleaned[-40:] or "action"


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
