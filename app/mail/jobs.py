"""Mail job executors: inbox_poll, send_request, reconcile_action.

Executors never bypass the engine's preflight; they re-check what must hold at
send time (current approval, approved recipients) and fail closed. Logs carry
job and case ids and error class names, never mail text or tokens.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import MailCursor, SqlEventBus
from app.engine.jobs import case_now, enqueue
from app.engine.runner import Executor, RunContext, register_executor
from app.mail.errors import MailError
from app.mail.health import MailboxWatch, apply_mailbox_health
from app.mail.inbound import process_inbound
from app.mail.match import bare_address
from app.mail.outbound import execute_followup, execute_send_request
from app.mail.outbound import reconcile_action as reconcile_outbound
from app.models import (
    Account,
    Action,
    ActionStatus,
    Approval,
    ApprovalStatus,
    Case,
    Job,
    Plan,
    PlanStatus,
    ProviderProfile,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 60
RECONCILE_DELAY_S = 30
MAX_RECONCILES = 3
__all__ = ["ensure_inbox_poll", "register_mail_executors"]


def ensure_inbox_poll(session: Session, case_id: UUID, *, now: datetime | None = None) -> Job:
    """Start the poll chain for a case. Safe to call again: the first key is fixed."""
    moment = now or datetime.now(UTC)
    case = session.get(Case, case_id)
    if case is None:
        raise MailError("Case not found")
    return enqueue(
        session,
        case_id=case_id,
        kind="inbox_poll",
        run_at_case_time=case_now(case, moment),
        idem_key=f"inbox_poll:{case_id}:0",
        payload={"seq": 0},
    )


async def inbox_poll(session: Session, job: Job, ctx: RunContext) -> None:
    """Poll the family mailbox once, ingest, and queue the next poll.

    Monitoring becomes `ok` only here, after a poll that succeeded. A failed poll
    interrupts monitoring and the next poll is still queued with the same cursor.
    """
    case = session.get(Case, job.case_id)
    if case is None:
        raise MailError("Case not found")
    payload = dict(job.payload or {})
    address = str(getattr(ctx.settings, "family_mailbox", "") or "")
    bus = SqlEventBus()
    now = datetime.now(UTC)
    raw_cursor = payload.get("cursor")
    cursor = MailCursor.model_validate(raw_cursor) if isinstance(raw_cursor, dict) else None
    next_cursor = cursor
    failure: str | None = None
    token_ok = True
    try:
        if ctx.mailbox is None or not address:
            raise MailError("The family mailbox is not configured")
        checker = getattr(ctx.mailbox, "token_valid", None)
        if callable(checker):
            token_ok = bool(checker(address))
        with session.begin_nested():
            messages, polled = await ctx.mailbox.poll(address, cursor)
            await process_inbound(session, messages, ai=ctx.ai, bus=bus, bound_case_id=case.id)
        next_cursor = polled
    except Exception as exc:  # noqa: BLE001 - recorded by class name, then monitoring is interrupted
        failure = type(exc).__name__
        logger.warning(
            "inbox poll failed",
            extra={"kind": "mail.poll_failed", "job_id": str(job.id), "error": failure},
        )
    watch = MailboxWatch(last_poll_at=now if failure is None else None, token_valid=token_ok)
    apply_mailbox_health(session, case, bus, watch, now=now)
    if failure is not None:
        bus.publish(
            session,
            case.id,
            "poll_failed",
            {"error": failure, "job_id": str(job.id)},
            actor="Afterward",
        )
    _queue_next_poll(session, case, payload, next_cursor, now)


def _queue_next_poll(
    session: Session,
    case: Case,
    payload: dict,
    cursor: MailCursor | None,
    now: datetime,
) -> None:
    seq = int(payload.get("seq", 0)) + 1
    interval = int(payload.get("interval_s", POLL_INTERVAL_S))
    nxt: dict = {"seq": seq, "interval_s": interval}
    if cursor is not None:
        nxt["cursor"] = cursor.model_dump()
    enqueue(
        session,
        case_id=case.id,
        kind="inbox_poll",
        run_at_case_time=case_now(case, now) + timedelta(seconds=interval),
        idem_key=f"inbox_poll:{case.id}:{seq}",
        payload=nxt,
    )


def approval_is_current(session: Session, payload: dict) -> bool:
    """The approval is approved, bound to this plan version and hash, and the plan is latest."""
    approval_id = payload.get("approval_id")
    if not approval_id:
        return False
    try:
        approval = session.get(Approval, UUID(str(approval_id)))
    except ValueError:
        return False
    if approval is None or approval.status is not ApprovalStatus.approved:
        return False
    plan = session.get(Plan, approval.plan_id)
    if plan is None or plan.status is not PlanStatus.approved:
        return False
    newest = session.scalar(
        select(Plan.id)
        .where(Plan.account_id == plan.account_id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    return (
        newest == plan.id
        and approval.plan_version == plan.version
        and approval.plan_hash == plan.hash
        and str(payload.get("plan_hash")) == plan.hash
        and int(payload.get("plan_version", -1)) == plan.version
    )


def _action_for(session: Session, job: Job) -> Action:
    payload = job.payload or {}
    action: Action | None = None
    if payload.get("action_id"):
        try:
            action = session.get(Action, UUID(str(payload["action_id"])))
        except ValueError:
            action = None
    elif payload.get("action_idem_key"):
        action = session.scalar(
            select(Action).where(Action.idem_key == str(payload["action_idem_key"]))
        )
    if action is None and payload.get("followup") and payload.get("account_id"):
        action = _followup_action(session, job)
    if action is None or action.case_id != job.case_id:
        raise MailError("No action for this job on this case")
    return action


def _followup_action(session: Session, job: Job) -> Action:
    """Build (once) the follow-up email action from the account's earlier sent request.

    The recipients, mailbox and thread are copied from that request, never from the job.
    """
    payload = job.payload or {}
    idem = f"followup:{payload.get('followup_job_id') or job.id}"
    existing = session.scalar(select(Action).where(Action.idem_key == idem))
    if existing is not None:
        return existing
    account_id = str(payload["account_id"])
    earlier = [
        row
        for row in session.scalars(
            select(Action)
            .where(Action.case_id == job.case_id, Action.kind == "email_send")
            .order_by(Action.created_at.desc())
        )
        if str((row.request or {}).get("account_id")) == account_id
        and row.status in {ActionStatus.sent, ActionStatus.reconciled}
        and not (row.request or {}).get("followup")
    ]
    if not earlier:
        raise MailError("No earlier sent request to follow up on")
    base = dict(earlier[0].request or {})
    request = {
        "account_id": account_id,
        "to_addrs": list(base.get("to_addrs") or []),
        "subject": base.get("subject") or "Account request",
        "mailbox": base.get("mailbox"),
        "thread_id": base.get("thread_id"),
        "in_reply_to": base.get("rfc_message_id"),
        "action_key": f"fu-{str(payload.get('followup_job_id') or job.id)[:8]}",
        "followup": True,
    }
    action = Action(
        case_id=job.case_id,
        kind="email_send",
        idem_key=idem,
        status=ActionStatus.pending,
        request={k: v for k, v in request.items() if v is not None},
    )
    session.add(action)
    session.flush()
    return action


def _approved_recipients(session: Session, action: Action) -> set[str]:
    raw = (action.request or {}).get("account_id")
    if not raw:
        return set()
    account = session.get(Account, UUID(str(raw)))
    if account is None or account.provider_id is None:
        return set()
    profile = session.get(ProviderProfile, account.provider_id)
    if profile is None:
        return set()
    return {bare_address(str(item)) for item in profile.approved_recipients}


def _deny(session: Session, action: Action, reason: str, bus: SqlEventBus) -> MailError:
    request = dict(action.request or {})
    request["blocked"] = reason
    action.request = request
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(action, "request")
    bus.publish(
        session,
        action.case_id,
        "send_blocked",
        {"reason": reason, "action_id": str(action.id)},
        actor="Afterward",
    )
    return MailError(reason)


async def send_request(session: Session, job: Job, ctx: RunContext) -> None:
    """Send one approved request. No current approval or an unapproved recipient means no send."""
    action = _action_for(session, job)
    bus = SqlEventBus()
    if action.status in {ActionStatus.sent, ActionStatus.reconciled}:
        return
    if action.kind == "email_send":
        if not approval_is_current(session, dict(job.payload or {})):
            raise _deny(session, action, "approval_invalid", bus)
        allowed = _approved_recipients(session, action)
        wanted = [bare_address(str(a)) for a in (action.request or {}).get("to_addrs") or []]
        if not wanted or any(addr not in allowed for addr in wanted):
            raise _deny(session, action, "recipient_not_approved", bus)
        family = str(getattr(ctx.settings, "family_mailbox", "") or "")
        if family and (action.request or {}).get("mailbox") != family:
            raise _deny(session, action, "mailbox_not_family", bus)
        if ctx.mailbox is None:
            raise MailError("The family mailbox is not configured")
    elif action.kind != "handoff":
        raise _deny(session, action, "unsupported_action_kind", bus)
    send = execute_followup if (job.payload or {}).get("followup") else execute_send_request
    await send(session, action, mailbox=ctx.mailbox, bus=bus)  # type: ignore[arg-type]
    if action.status is ActionStatus.uncertain:
        _queue_reconcile(session, job, action)


def _queue_reconcile(session: Session, job: Job, action: Action) -> None:
    case = session.get(Case, action.case_id)
    if case is None:
        return
    carry = {
        key: value
        for key, value in (job.payload or {}).items()
        if key in {"plan_id", "plan_version", "plan_hash", "approval_id"}
    }
    enqueue(
        session,
        case_id=case.id,
        kind="reconcile_action",
        run_at_case_time=case_now(case, datetime.now(UTC)) + timedelta(seconds=RECONCILE_DELAY_S),
        idem_key=f"reconcile:{action.id}:{action.attempts}",
        payload={"action_id": str(action.id), **carry},
    )


async def reconcile_action(session: Session, job: Job, ctx: RunContext) -> None:
    """Look in Sent for the footer. Re-send only while the approval is still current."""
    action = _action_for(session, job)
    if ctx.mailbox is None:
        raise MailError("The family mailbox is not configured")
    if action.status in {ActionStatus.sent, ActionStatus.reconciled}:
        return
    if approval_is_current(session, dict(job.payload or {})):
        await reconcile_outbound(session, action, ctx.mailbox)  # type: ignore[arg-type]
    else:
        footer = str((action.request or {}).get("footer_ref") or "")
        name = str((action.request or {}).get("mailbox") or "")
        found = await ctx.mailbox.search_sent(name, footer) if footer and name else None
        if found is not None:
            action.status = ActionStatus.reconciled
            action.external_id = found.gmail_id
        else:
            action.status = ActionStatus.uncertain
    if action.status is ActionStatus.uncertain and action.attempts < MAX_RECONCILES:
        _queue_reconcile(session, job, action)


def register_mail_executors(register: Callable[[str, Executor], None] = register_executor) -> None:
    """Register the mail executors with the job runner."""
    register("inbox_poll", inbox_poll)
    register("send_request", send_request)
    register("reconcile_action", reconcile_action)
