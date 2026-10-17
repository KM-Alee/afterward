"""Project database rows into the desk's CaseBoard. Everything shown is read from rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.coverage import NOT_SEARCHED, WHERE_ELSE
from app.discovery.directory import track_for
from app.engine.status import classify_account
from app.models import (
    Account,
    AccountOrigin,
    Action,
    ActionStatus,
    Approval,
    ApprovalStatus,
    Case,
    Commitment,
    DiscoverySource,
    DocsStatus,
    Event,
    Job,
    JobStatus,
    MailConnection,
    Member,
    MemberRole,
    Message,
    MessageDirection,
    MoneyStatus,
    OutcomeCheck,
    Ownership,
    Plan,
    ProviderProfile,
    RecipientCheck,
    ServiceStatus,
)
from app.story import condition_label, verdict_text
from app.web.state import (
    AccountTile,
    CaseBoard,
    Check,
    ClockCase,
    CoverageView,
    Dim,
    FinishLine,
    OutcomePanel,
    ScheduledJob,
    TimelineEvent,
)

DEMO_REF = "AW-1042"
SOURCE_LABEL = "Live from the database"

_SERVICE = {
    ServiceStatus.active: Dim("neutral", "Active, nothing requested"),
    ServiceStatus.requested: Dim("progress", "Request sent"),
    ServiceStatus.acknowledged: Dim("waiting", "Acknowledged, not done"),
    ServiceStatus.blocked: Dim("review", "Blocked on a requirement"),
    ServiceStatus.closed: Dim("holding", "Closed"),
    ServiceStatus.transferred: Dim("holding", "Transferred"),
    ServiceStatus.frozen: Dim("holding", "Frozen"),
}
_MONEY = {
    MoneyStatus.none: Dim("neutral", "No money tracked"),
    MoneyStatus.needs_review: Dim("review", "A charge needs review"),
    MoneyStatus.likely_error: Dim("violated", "Likely billing error"),
    MoneyStatus.refund_promised: Dim("waiting", "Refund promised"),
    MoneyStatus.issued_awaiting_receipt: Dim("waiting", "Refund issued: not yet on a statement"),
    MoneyStatus.received: Dim("holding", "Refund received"),
    MoneyStatus.balance_owed: Dim("review", "Balance owed"),
    MoneyStatus.dispute_open: Dim("review", "Dispute open"),
}
_DOCS = {
    DocsStatus.none_needed: Dim("neutral", "None needed"),
    DocsStatus.requested: Dim("review", "Provider asked for documents"),
    DocsStatus.requirement_unmet: Dim("violated", "Requirement not met"),
    DocsStatus.sent: Dim("info", "Sent"),
    DocsStatus.accepted: Dim("holding", "Accepted"),
}
_BUCKET = {
    "unconfirmed": ("review", "Unconfirmed"),
    "blocked": ("review", "Blocked"),
    "handed_back": ("info", "With family"),
    "promised": ("waiting", "Promised"),
    "confirmed": ("holding", "Done"),
    "open": ("progress", "Open"),
}
_EVENT_TEXT = {
    "clock.advanced": "Demo clock moved forward.",
    "followup.queued": "A follow-up was queued under the same approved plan.",
    "mail_ingested": "A reply arrived and was read.",
    "inbox.poll": "The mailbox was checked.",
    "digest.sent": "A weekly summary went to the family.",
}
_JOB_LABEL = {
    "followup": "Follow-up",
    "send_request": "Send an approved request",
    "inbox_poll": "Check the mailbox",
    "health_check": "Health check",
    "reconcile_action": "Check the Sent folder",
    "final_bill_check": "Final bill check",
    "refund_evidence_check": "Refund check",
    "digest": "Weekly summary",
}


def resolve_case(session: Session, case_id: UUID) -> Case | None:
    """The row for a desk id. The fixed demo id points at the seeded demo case by reference."""
    from app.web.state import DEMO_CASE_ID

    case = session.get(Case, case_id)
    if case is None and case_id == DEMO_CASE_ID:
        case = session.scalar(select(Case).where(Case.ref == DEMO_REF, Case.is_demo.is_(True)))
    return case


def _stamp(moment: datetime | None) -> str:
    if moment is None:
        return ""
    moment = moment.astimezone(UTC)
    return f"{moment.day} {moment.strftime('%b %Y, %H:%M')} UTC"


def _origin_label(account: Account, owner: str) -> str:
    evidence = (account.origin_evidence or "").casefold()
    if account.origin is AccountOrigin.inbox:
        if evidence.startswith("his inbox"):
            return f"His inbox (connected by {owner})"
        return "Household inbox"
    if account.origin is AccountOrigin.forwarded:
        return "Forward"
    if account.origin is AccountOrigin.photo:
        return "Photo"
    return "Said by family"


def _provider_name(account: Account, profiles: dict[UUID, ProviderProfile]) -> str:
    profile = profiles.get(account.provider_id) if account.provider_id else None
    if profile is not None:
        return profile.name
    named = (account.next_step or {}).get("provider")
    return str(named) if named else account.service_label


def _next(account: Account, provider: str, owner: str) -> tuple[str, str]:
    step = account.next_step or {}
    action = str(step.get("action") or "")
    who = str(step.get("owner") or "")
    if account.ownership is Ownership.unconfirmed:
        return owner, "Say whose this is"
    if account.ownership is Ownership.not_theirs:
        return "—", "Left out. Not his"
    names = {"family": owner, "provider": provider}
    if not action:
        return "—", "Nothing to do"
    return names.get(who, who.capitalize() or "—"), action


def _verdict_chip(verdict: str) -> tuple[str, str] | None:
    return {
        "needs_decision": ("violated", "Needs family"),
        "resolved": ("holding", "Done"),
        "open": ("unknown", "Unclear reply"),
    }.get(verdict)


def _checks(results: dict) -> list[Check]:
    out: list[Check] = []
    for key, state in results.items():
        if key == "action":
            continue
        label = condition_label(key)
        if state == "violated":
            out.append(Check(label, "violated", "Broken", "The reply breaks this condition."))
        elif state == "matched":
            out.append(Check(label, "holding", "Holding"))
        else:
            out.append(Check(label, "unknown", "Not stated", "The reply does not say."))
    return out


def project_board(session: Session, case_id: UUID, *, overlay: CaseBoard | None = None):
    """Build the desk from rows. `overlay` is the in-memory board; only its story events,
    threads, family choice and a simulated reply (when no real one exists) are added."""
    case = resolve_case(session, case_id)
    if case is None:
        return None
    owner_member = session.scalar(
        select(Member).where(Member.case_id == case.id, Member.role == MemberRole.owner)
    )
    owner = (owner_member.name.split()[0]) if owner_member else "Family"
    accounts = list(
        session.scalars(
            select(Account).where(Account.case_id == case.id).order_by(Account.created_at)
        )
    )
    profiles = {p.id: p for p in session.scalars(select(ProviderProfile))}
    plans = list(session.scalars(select(Plan).where(Plan.case_id == case.id)))
    approvals = list(session.scalars(select(Approval).where(Approval.case_id == case.id)))
    checks = list(
        session.scalars(
            select(OutcomeCheck)
            .where(OutcomeCheck.case_id == case.id)
            .order_by(OutcomeCheck.created_at)
        )
    )
    commitments = list(
        session.scalars(
            select(Commitment).where(Commitment.case_id == case.id).order_by(Commitment.created_at)
        )
    )
    messages = {m.id: m for m in session.scalars(select(Message).where(Message.case_id == case.id))}
    latest_check: dict[UUID, OutcomeCheck] = {c.account_id: c for c in checks}
    latest_plan: dict[UUID, Plan] = {}
    for plan in sorted(plans, key=lambda p: p.version):
        latest_plan[plan.account_id] = plan
    approved_for = {a.plan_id for a in approvals if a.status is ApprovalStatus.approved}
    open_for = {a.plan_id for a in approvals if a.status is ApprovalStatus.open}
    names = {a.id: _provider_name(a, profiles) for a in accounts}

    tiles: list[AccountTile] = []
    finish: list[FinishLine] = []
    for account in accounts:
        provider = names[account.id]
        bucket_key = classify_account(account)
        if account.ownership is Ownership.not_theirs:
            bucket = ("void", "Not his")
        else:
            bucket = _BUCKET[bucket_key]
        check = latest_check.get(account.id)
        chip = _verdict_chip(check.verdict) if check is not None else None
        if chip is not None and account.ownership is Ownership.confirmed:
            bucket = chip
        who, what = _next(account, provider, owner)
        plan = latest_plan.get(account.id)
        plan_line = ""
        if plan is not None:
            state = (
                "approved by the family"
                if plan.id in approved_for
                else ("waiting for approval" if plan.id in open_for else plan.status.value)
            )
            plan_line = (
                f"Plan v{plan.version}: {plan.action.value} to {plan.recipient or 'no recipient'} "
                f"(from the provider profile), {state}."
            )
        lines = [
            Check(
                f"{c.action.value} ({c.status.value})",
                "info" if c.quote_verified else "unknown",
                "Quote found in the message" if c.quote_verified else "Quote not verified",
                c.evidence_quote,
            )
            for c in commitments
            if c.account_id == account.id
        ]
        tiles.append(
            AccountTile(
                id=str(account.id),
                name=provider,
                label=account.service_label,
                origin=_origin_label(account, owner),
                bucket_kind=bucket[0],
                bucket_text=bucket[1],
                service=_SERVICE[account.status_service],
                money=_MONEY[account.status_money],
                docs=_DOCS[account.status_docs],
                next_owner=who,
                next_action=what,
                focus=bool(check is not None and check.verdict == "needs_decision"),
                conditions=_checks(check.results) if check is not None else [],
                origin_detail=account.origin_evidence or "",
                track=account.track or track_for(provider),
                plan_line=plan_line,
                commitments=lines,
            )
        )
        finish.append(FinishLine(bucket[0], bucket[1], f"{provider}, {account.service_label}"))

    outcome = _outcome(session, accounts, names, latest_plan, checks, commitments, messages)
    simulated = False
    if outcome is None and overlay is not None and overlay.outcome is not None:
        outcome = overlay.outcome
        simulated = True

    events = _events(session, case, messages)
    if overlay is not None:
        events = events + list(overlay.events)

    open_counts = sum(1 for t in tiles if t.bucket_text != "Done")
    unconfirmed = [t for t in tiles if t.bucket_text == "Unconfirmed"]
    lead = (
        f"Not everything. {open_counts} of {len(tiles)} accounts are not done."
        if open_counts
        else "Everything we track has written evidence. The list itself is not complete."
    )
    clock_now = datetime.now(UTC) + timedelta(seconds=int(case.clock_offset_s))
    board = CaseBoard(
        id=case_id,
        deceased=case.deceased_name,
        died=case.date_of_death.strftime("%-d %B %Y") if case.date_of_death else "",
        handler=(
            f"{owner_member.name.split()[0]} is handling the estate (as she has told us)."
            if owner_member
            else ""
        ),
        empty=not accounts,
        is_demo=case.is_demo,
        clock_case=ClockCase(clock_offset_s=int(case.clock_offset_s), is_demo=case.is_demo),
        monitoring=case.monitoring.value,
        delivery=_delivery(session, case),
        accounts=tiles,
        outcome=outcome,
        events=events,
        threads=dict(overlay.threads) if overlay is not None else {},
        family_choice=overlay.family_choice if overlay is not None else None,
        source="database",
        source_label=SOURCE_LABEL,
        case_time=_stamp(clock_now),
        outcome_simulated=simulated,
        finish_lead=lead,
        finish_note=(
            f"{len(unconfirmed)} candidate accounts still unconfirmed. "
            "Confirmed, promised, blocked, handed back and unconfirmed stay separate."
        ),
        finish_lines=finish,
        coverage=_coverage(session, case, owner, unconfirmed),
        scheduled=_scheduled(session, case, names, clock_now),
    )
    return board


def _delivery(session: Session, case: Case) -> str:
    states = set(session.scalars(select(Action.status).where(Action.case_id == case.id)).all())
    if ActionStatus.uncertain in states:
        return "uncertain"
    if ActionStatus.reconciled in states:
        return "reconciled"
    return "ok"


def _outcome(session, accounts, names, latest_plan, checks, commitments, messages):
    if not checks:
        return None
    check = checks[-1]
    account = next((a for a in accounts if a.id == check.account_id), None)
    if account is None:
        return None
    plan = session.scalar(
        select(Plan).where(Plan.account_id == account.id, Plan.version == check.plan_version)
    ) or latest_plan.get(account.id)
    conditions = [condition_label(str(c.get("key"))) for c in (plan.conditions if plan else [])]
    mine = [c for c in commitments if c.account_id == account.id]
    message = messages.get(mine[-1].message_id) if mine else None
    quote = message.latest_text if message is not None else ""
    in_writing = message is not None and message.recipient_check is RecipientCheck.approved
    verdict = type("V", (), {})()
    verdict.verdict = check.verdict
    verdict.results = dict(check.results or {})
    kind = {"resolved": "resolved", "needs_decision": "notdone"}.get(check.verdict, "open")
    provider = names[account.id]
    return OutcomePanel(
        title=f"{provider}, {account.service_label}",
        plan_version=check.plan_version,
        requested=(
            f"{plan.action.value.replace('_', ' ').capitalize()}: {account.service_label}."
            if plan
            else ""
        ),
        requested_conditions=conditions,
        quote=quote,
        quote_evidence="writing" if in_writing else "unverified",
        quote_at=_stamp(message.received_at if message else None),
        verdict_kind=kind,
        verdict_text=verdict_text(verdict),  # type: ignore[arg-type]
        checks=_checks(verdict.results),
        provider=provider,
    )


def _events(session: Session, case: Case, messages) -> list[TimelineEvent]:
    rows: list[tuple[datetime, TimelineEvent]] = []
    for event in session.scalars(select(Event).where(Event.case_id == case.id)):
        if event.kind == "mail_ingested" and messages:
            continue  # the message itself is listed below
        text = (
            _EVENT_TEXT.get(event.kind)
            or event.kind.replace("_", " ").replace(".", ": ").capitalize() + "."
        )
        if event.kind == "clock.advanced":
            seconds = int((event.payload or {}).get("seconds") or 0)
            text = f"Demo clock moved forward {seconds // 86400} days."
        actor = event.actor.casefold()
        tone = "family" if actor in {"family", "sara", "amina"} else "system"
        if actor == "provider":
            tone = "provider"
        rows.append((event.ts, TimelineEvent(text, _stamp(event.ts), "unverified", tone)))
    for message in messages.values():
        when = message.received_at or message.created_at
        if message.direction is MessageDirection.inbound:
            writing = message.recipient_check is RecipientCheck.approved
            held = "" if writing else " It did not come from an approved address, so it is held."
            rows.append(
                (
                    when,
                    TimelineEvent(
                        f"A reply arrived: {message.subject or 'no subject'}.{held}",
                        _stamp(when),
                        "writing" if writing else "unverified",
                        "provider",
                        message.latest_text[:400],
                    ),
                )
            )
        else:
            rows.append(
                (
                    when,
                    TimelineEvent(
                        f"A request went to {', '.join(message.to_addrs) or 'a provider'}.",
                        _stamp(when),
                        "unverified",
                        "system",
                    ),
                )
            )
    rows.sort(key=lambda pair: pair[0])
    return [event for _when, event in rows]


def _scheduled(session: Session, case: Case, names, clock_now: datetime) -> list[ScheduledJob]:
    out: list[ScheduledJob] = []
    jobs = session.scalars(
        select(Job)
        .where(Job.case_id == case.id, Job.status == JobStatus.pending)
        .order_by(Job.run_at_case_time)
    )
    for job in jobs:
        if job.kind in {"health_check", "inbox_poll"}:
            continue
        label = _JOB_LABEL.get(job.kind, job.kind.replace("_", " ").capitalize())
        account_id = ((job.payload or {}).get("reason") or {}).get("account_id")
        try:
            who = names.get(UUID(str(account_id))) if account_id else None
        except ValueError:
            who = None
        due = job.run_at_case_time
        state = "due" if due <= clock_now else "scheduled"
        out.append(ScheduledJob(f"{label}{': ' + who if who else ''}", _stamp(due), state))
    return out


def _coverage(session: Session, case: Case, owner: str, unconfirmed) -> CoverageView:
    searched: list[str] = []
    waiting: list[str] = []
    for source in session.scalars(
        select(DiscoverySource).where(DiscoverySource.case_id == case.id)
    ):
        line = f"{source.kind.replace('_', ' ').capitalize()}: {source.scope_text}".strip(": ")
        if source.status in {"waiting", "started"}:
            waiting.append(
                f"{line} (started by {source.started_by or 'the family'}, result not back)"
            )
        else:
            searched.append(f"{line} ({source.matched} matched, {source.read} read with OK)")
    connections = list(
        session.scalars(
            select(MailConnection).where(
                MailConnection.case_id == case.id, MailConnection.revoked_at.is_(None)
            )
        )
    )
    his = False
    for conn in connections:
        if conn.account_of == "deceased":
            his = True
            searched.append(f"His inbox, connected by {conn.owner_label or owner} (read-only)")
        else:
            searched.append(f"{conn.owner_label or owner}'s household inbox (read-only)")
    counts: dict[str, int] = {}
    for account in session.scalars(select(Account).where(Account.case_id == case.id)):
        counts[account.origin.value] = counts.get(account.origin.value, 0) + 1
    for key, label in (
        ("forwarded", "forwarded emails"),
        ("photo", "photos of bills and letters"),
        ("manual", "accounts the family told us about"),
    ):
        if counts.get(key):
            searched.append(f"{counts[key]} {label}")
    return CoverageView(
        searched=searched,
        waiting=waiting,
        not_searched=[item for item in NOT_SEARCHED if not (his and item == NOT_SEARCHED[0])]
        + ["Government, court and tax records", "His credit file"],
        needs_you=[t.label for t in unconfirmed],
        where_else=list(WHERE_ELSE),
    )
