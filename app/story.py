"""One Malik story: Telegram turns, the approved request and provider replies share one desk.

Code builds every recipient, sentence and verdict here. Model output only arrives as
verified commitment records, and an ambiguous record never becomes a broken condition.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from app.ai.schemas import CommitmentOut
from app.contracts import SendRequest
from app.engine.outcome import (
    CommitmentView,
    Condition,
    FactView,
    PlanView,
    Verdict,
    conditions_from,
    outcome_check,
)
from app.web.state import (
    DEMO_CASE_ID,
    CaseBoard,
    Check,
    Dim,
    SurfaceState,
    TimelineEvent,
    case_time_label,
)

logger = logging.getLogger(__name__)

NORTHLINE_REF = "4417"
NORTHLINE_SUBJECT = "Line ending 4417"
NORTHLINE_FOOTER = "AW-1042-NL1"
NORTHLINE_RECIPIENT = "bereavement@northline.example"
CASE_REFS = (
    "4417",
    "2290",
    "0932",
    "CP-77120",
    "SB-88213",
    "FL-5531",
    "HW-20418",
    "ML-6610",
    "PB-3017",
)
NORTHLINE_PLAN = PlanView(
    action="transfer",
    conditions=(
        Condition("voicemail_preserved", "bool", "true"),
        Condition("number_kept", "bool", "true"),
        Condition("contract_months", "max_int", "0"),
    ),
    completion_evidence=("transfer_confirmation",),
)
CONDITION_LABELS = {
    "voicemail_preserved": "Voicemail kept",
    "number_kept": "Number kept",
    "contract_months": "No new contract",
}
_FACT_FOR = {
    "voicemail_preserved": "voicemail_preserved",
    "number_kept": "number_kept",
    "contract_months": "contract_months",
}


def views_for(commitments: Sequence[CommitmentOut], at: datetime) -> list[CommitmentView]:
    """Verified records as outcome-check inputs. An unclear scope means this service."""
    return [
        CommitmentView(
            action=item.action,
            status=item.status,
            interpretation=item.interpretation,
            facts=tuple(FactView(fact.key, fact.value, fact.evidence_quote) for fact in item.facts),
            negated=item.negated,
            at=at,
            evidence_quote=item.evidence_quote,
            scope="this_service" if item.scope == "unclear" else item.scope,
        )
        for item in commitments
    ]


def condition_label(key: str) -> str:
    """Plain label for a plan condition key. Unknown keys are spelled out, never hidden."""
    return CONDITION_LABELS.get(key) or key.replace("_", " ").strip().capitalize()


def plan_view_from_row(plan: Any, completion_evidence: Sequence[str] = ()) -> PlanView:
    """The approved Plan row as the outcome check's input. Nothing here is Northline-specific."""
    return PlanView(
        action=plan.action.value if hasattr(plan.action, "value") else str(plan.action),
        conditions=conditions_from(list(plan.conditions or [])),
        completion_evidence=tuple(str(item) for item in completion_evidence),
    )


async def read_reply(
    ai: Any,
    text: str,
    *,
    account_ref: str,
    case_refs: Sequence[str],
    plan: PlanView,
) -> tuple[Verdict, list[CommitmentOut]]:
    """Read one reply on an account's thread and compare it with that account's approved plan."""
    from app.engine.pipeline import extract_verified_reply

    reply = await extract_verified_reply(ai, text, tuple(case_refs), thread_ref=account_ref)
    mine = [item for item in reply.commitments if item.account_hint == account_ref]
    verdict = outcome_check(plan, views_for(mine, datetime.now(UTC)))
    return verdict, mine


async def read_northline_reply(ai: Any, text: str) -> tuple[Verdict, list[CommitmentOut]]:
    """In-memory demo only (no database): the scripted Northline plan stands in for the rows."""
    return await read_reply(
        ai, text, account_ref=NORTHLINE_REF, case_refs=CASE_REFS, plan=NORTHLINE_PLAN
    )


def approved_plan_for(session: Any, account_id: Any) -> tuple[Any, Any] | None:
    """The latest approved Plan and its approved Approval for an account, or None."""
    from sqlalchemy import select

    from app.models import Approval, ApprovalStatus, Plan, PlanStatus

    plan = session.scalar(
        select(Plan)
        .where(Plan.account_id == account_id, Plan.status == PlanStatus.approved)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    if plan is None:
        return None
    approval = session.scalar(
        select(Approval).where(
            Approval.plan_id == plan.id,
            Approval.plan_hash == plan.hash,
            Approval.status == ApprovalStatus.approved,
        )
    )
    if approval is None:
        return None
    return plan, approval


def _quote_for(key: str, commitments: Sequence[CommitmentOut]) -> str:
    for item in commitments:
        if item.interpretation != "clear":
            continue
        for fact in item.facts:
            if fact.key == _FACT_FOR.get(key, key):
                return fact.evidence_quote
    return ""


def checks_for(verdict: Verdict, commitments: Sequence[CommitmentOut] = ()) -> list[Check]:
    """One row per approved condition. Missing stays 'Not stated', never 'Broken'."""
    checks: list[Check] = []
    for key, state in verdict.results.items():
        if key == "action":
            continue
        label = condition_label(key)
        quote = _quote_for(key, commitments)
        if state == "violated":
            why = (
                f"The reply says: \u201c{quote}\u201d"
                if quote
                else "The reply breaks this condition."
            )
            checks.append(Check(label, "violated", "Broken", why))
        elif state == "matched":
            checks.append(
                Check(label, "holding", "Holding", f"\u201c{quote}\u201d" if quote else "")
            )
        else:
            checks.append(Check(label, "unknown", "Not stated", "The reply does not say."))
    if "price_change" in verdict.extras:
        checks.append(
            Check("Price", "unauthorised", "Not approved", "A price was not in the plan.")
        )
    return checks


def verdict_text(verdict: Verdict) -> str:
    """Plain sentence for the desk. Only 'resolved' is done."""
    if verdict.verdict == "resolved":
        return "Done. The reply meets every approved condition."
    if verdict.verdict == "needs_decision":
        keys = [key for key in verdict.results if key != "action"]
        broken = [condition_label(k).lower() for k in keys if verdict.results[k] == "violated"]
        unstated = [condition_label(k).lower() for k in keys if verdict.results[k] == "missing"]
        parts = ["Not done."]
        if broken:
            parts.append(f"Broken: {', '.join(broken)}.")
        if unstated:
            parts.append(f"Not stated: {', '.join(unstated)}.")
        parts.append("Sara decides what happens next.")
        return " ".join(parts)
    return "Not treated as done. The reply is not clear enough to close this."


def publish(surface: SurfaceState, kind: str, summary: str, actor: str) -> None:
    surface.live.publish(DEMO_CASE_ID, kind, {"summary": summary}, actor=actor)


def add_event(
    surface: SurfaceState,
    text: str,
    *,
    evidence: str,
    tone: str,
    quote: str = "",
) -> None:
    board = surface.cases[DEMO_CASE_ID]
    board.events.append(TimelineEvent(text, case_time_label(surface, board), evidence, tone, quote))


def _northline_tile(board: CaseBoard):
    return next((tile for tile in board.accounts if tile.id == "nl4417"), None)


def show_northline_verdict(
    surface: SurfaceState,
    board: CaseBoard,
    text: str,
    verdict: Verdict,
    commitments: Sequence[CommitmentOut] = (),
) -> None:
    """Put the reply beside the approved conditions on the desk and the family card."""
    if board.outcome is None:
        return
    checks = checks_for(verdict, commitments)
    board.outcome.quote = text
    board.outcome.quote_evidence = "writing"
    board.outcome.quote_at = case_time_label(surface, board)
    board.outcome.verdict_kind = {"resolved": "resolved", "needs_decision": "notdone"}.get(
        verdict.verdict, "open"
    )
    board.outcome.verdict_text = verdict_text(verdict)
    board.outcome.checks = checks
    board.family_choice = None
    tile = _northline_tile(board)
    if tile is not None:
        tile.conditions = checks
        if verdict.verdict == "resolved":
            tile.bucket_kind, tile.bucket_text = "holding", "Done"
            tile.service = Dim("holding", "Transferred, conditions met")
            tile.next_owner, tile.next_action = "—", "Nothing to do"
        elif verdict.verdict == "needs_decision":
            tile.bucket_kind, tile.bucket_text = "violated", "Needs family"
            tile.service = Dim("review", "Reported done: not accepted")
            tile.next_owner, tile.next_action = "Sara", "Decide: correction, call, or accept"
        else:
            tile.bucket_kind, tile.bucket_text = "unknown", "Unclear reply"
            tile.service = Dim("unknown", "Reply not clear enough to close")
            tile.next_owner, tile.next_action = "Afterward", "Ask Northline to confirm in writing"
    add_event(
        surface,
        f"Outcome check: {board.outcome.verdict_text}",
        evidence="unverified",
        tone="system",
        quote=text,
    )


def mark_plan_revised(surface: SurfaceState, conversation: Any) -> None:
    """Amina's answer changed the plan. The desk shows the new plan waiting for Sara."""
    board = surface.cases[DEMO_CASE_ID]
    plan = getattr(conversation.state, "plan", None)
    if plan is None or board.outcome is None:
        return
    transfer = next((item for item in plan.items if item.action == "transfer"), None)
    if transfer is None or getattr(board, "story_plan", None) is plan:
        return
    board.story_plan = plan  # type: ignore[attr-defined]
    board.outcome.plan_version += 1
    board.outcome.requested = (
        f"{transfer.action_text[:1].upper()}{transfer.action_text[1:]}: "
        f"{transfer.account_label}, only if every condition holds."
    )
    board.outcome.requested_conditions = [label.capitalize() for label in transfer.condition_labels]
    board.outcome.quote = "No reply yet."
    board.outcome.quote_evidence = "unverified"
    board.outcome.quote_at = ""
    board.outcome.verdict_kind = "open"
    board.outcome.verdict_text = "Waiting for Sara to approve this plan."
    board.outcome.checks = [
        Check(CONDITION_LABELS[key], "unknown", "Not stated") for key in CONDITION_LABELS
    ]
    board.family_choice = None
    tile = _northline_tile(board)
    if tile is not None:
        tile.bucket_kind, tile.bucket_text = "review", "Needs Sara"
        tile.service = Dim("review", "Plan changed: transfer, not close")
        tile.next_owner, tile.next_action = "Sara", "Approve the revised plan"
        tile.conditions = list(board.outcome.checks)
    held = [item.provider for item in plan.items if item.action == "hold"]
    summary = "Amina's answer changed the plan: transfer line 4417 to her, keep the number"
    if "voicemail_preserved" in transfer.conditions:
        summary += " and the voicemail"
    summary += ", no new contract"
    if held:
        summary += f"; do not close {', '.join(held)}"
    add_event(surface, summary + ".", evidence="family", tone="family")


def approval_body(card: Any) -> str:
    """The approved request, built from the card. The recipient is not in the body."""
    return (
        "Dear Northline bereavement team,\n\n"
        "We act for the family of Yusuf Malik, who died on 3 March 2026.\n"
        f"Account: {card.account}\n"
        f"Request: {card.action}\n"
        f"Conditions: {'; '.join(card.conditions)}\n"
        f"If a condition cannot be met: {card.fallback}. Please reply before acting.\n\n"
        "Afterward, an AI assistant acting for the family. A person approved this request.\n\n"
        f"Ref {NORTHLINE_FOOTER}"
    )


async def send_approved_request(
    settings: Any, card: Any, *, approved_recipients: Sequence[str] | None = None
) -> bool:
    """Send the approved card through Gmail. The demo provider inbox stands in for Northline.

    With a database, pass the recipients of the approved Plan rows; without one, the scripted
    Northline address is the only one allowed.
    """
    allowed = (
        tuple(approved_recipients) if approved_recipients is not None else (NORTHLINE_RECIPIENT,)
    )
    if card is None or card.recipient not in allowed:
        return False
    if not mail_ready(settings):
        return False
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "family")
        await mailbox.send(
            SendRequest(
                mailbox=settings.family_mailbox,
                to_addrs=[settings.providers_mailbox],
                subject=NORTHLINE_SUBJECT,
                text=approval_body(card),
                footer_ref=NORTHLINE_FOOTER,
                from_name="Afterward for the Malik family",
            )
        )
    except Exception:
        logger.info("approved request", extra={"kind": "mail.request", "ok": False})
        return False
    return True


async def add_reply_reminder(settings: Any) -> str:
    """One reminder to check Northline's reply. Fastn first, then Google Calendar."""
    if not mail_ready(settings):
        return ""
    if await _fastn_reminder(settings):
        return "fastn"
    from app.integrations.google import calendar_transport_for
    from app.mail.calendar import calendar_body

    start = (datetime.now(UTC) + timedelta(days=10)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    body = calendar_body(
        {
            "summary": "Afterward: check Northline's written reply (line 4417)",
            "start": start.isoformat(),
            "end": (start + timedelta(minutes=30)).isoformat(),
        }
    )
    try:
        transport = calendar_transport_for(settings)
        await asyncio.to_thread(transport.insert_event, body)
    except Exception:
        logger.info("reply reminder", extra={"kind": "calendar.insert", "ok": False})
        return ""
    return "google"


def fastn_reminder_succeeded(status_code: int, body: object) -> bool:
    """True only when Fastn reports a created workflow run. A bare 200 is not enough."""
    if status_code >= 300 or not isinstance(body, dict):
        return False
    return bool(body.get("id") or body.get("executionId") or body.get("ok") is True)


async def _fastn_reminder(settings: Any) -> bool:
    """Run a configured Fastn workflow. Without a workflow id, use Google Calendar."""
    secret = getattr(settings, "fastn_api_key", None)
    key = secret.get_secret_value() if secret is not None else ""
    host = str(getattr(settings, "fastn_api_host", "") or "").rstrip("/")
    workflow_id = str(getattr(settings, "fastn_workflow_id", "") or "")
    if not key or not host or not workflow_id:
        return False
    import httpx

    headers = {"Authorization": f"Bearer {key}"}
    if key.startswith("fsk_test_"):
        headers["X-fastn-Test-Mode"] = "true"
        headers["x-fastn-env"] = "test"
    try:
        response = await httpx.AsyncClient(timeout=15).post(
            f"{host}/api/v1/workflows/{workflow_id}/execute",
            headers=headers,
            json={"input": {"summary": "Check Northline's written reply for line 4417"}},
        )
        return fastn_reminder_succeeded(response.status_code, response.json())
    except Exception:
        logger.info("reply reminder", extra={"kind": "calendar.fastn", "ok": False})
        return False


def mail_ready(settings: Any) -> bool:
    if settings is None:
        return False
    return bool(
        settings.family_mailbox
        and settings.providers_mailbox
        and settings.google_client_id.get_secret_value()
        and settings.google_refresh_token_family.get_secret_value()
    )


async def mark_request_sent(surface: SurfaceState, settings: Any, card: Any) -> str:
    """After Sara's approval: send once, add the reminder, and show both on the desk."""
    board = surface.cases[DEMO_CASE_ID]
    sent = await send_approved_request(settings, card)
    reminder = await add_reply_reminder(settings) if sent else ""
    if sent:
        text = "Sara approved the plan on Telegram. The request went to Northline by Gmail."
        reply = (
            "Sent to Northline through the connected Gmail mailbox. I'll compare their reply "
            "with your conditions before anything is marked done."
        )
    else:
        text = "Sara approved the plan on Telegram. The mailbox is not set, so nothing was sent."
        reply = "Approved, but the mailbox is not set up, so nothing was sent."
    add_event(surface, text, evidence="family", tone="family")
    if reminder == "fastn":
        note = "Calendar reminder added through Fastn. Direct Calendar stays the backup."
    elif reminder == "google":
        note = "Calendar reminder added through Google Calendar."
    else:
        note = ""
    if note:
        add_event(surface, note, evidence="unverified", tone="system")
    if board.outcome is not None and sent:
        board.outcome.verdict_text = "Waiting for Northline's written reply."
        tile = _northline_tile(board)
        if tile is not None:
            tile.bucket_kind, tile.bucket_text = "waiting", "Waiting"
            tile.service = Dim("progress", "Request sent, waiting for a reply")
            tile.next_owner, tile.next_action = "Northline", "Reply in writing"
    publish(surface, "request.sent" if sent else "request.held", text, "family")
    return reply


_TURN_EVENTS = {
    "intake_card": ("Sara told us once on Telegram. We read the summary back to her.", "family"),
    "intake_confirmed": ("Sara confirmed the summary on Telegram.", "family"),
    "invite_joined": ("Amina joined the case from her invite link.", "family"),
    "dependency_question": ("Asked Amina about line 4417 before changing anything.", "system"),
    "approval_refused": ("Only Sara can approve. Nothing was sent.", "system"),
    "approval_held": ("The case is on hold. The approval did not send anything.", "system"),
    "decision_card": (
        "A decision in free text was read back as buttons. Nothing changed.",
        "system",
    ),
    "decision_recorded": ("Sara chose with a button. No organisation was contacted.", "family"),
    "finish": ("Sara asked if everything is finished. We gave the honest answer.", "system"),
    "crisis": ("The conversation paused for care. Admin waits.", "system"),
}


def reflect_turn(surface: SurfaceState, conversation: Any, kinds: Sequence[str]) -> None:
    """Mirror one Telegram turn onto the desk. Message bodies are not copied."""
    changed = False
    for kind in kinds:
        if kind == "plan_revision":
            mark_plan_revised(surface, conversation)
            changed = True
            continue
        row = _TURN_EVENTS.get(kind)
        if row is None:
            continue
        text, tone = row
        add_event(surface, text, evidence="family" if tone == "family" else "unverified", tone=tone)
        changed = True
    if changed:
        publish(surface, "telegram.turn", "Telegram updated the case", "family")
