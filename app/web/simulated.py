"""Paths that stay in memory and are labelled as simulated on the pages.

They run only when there is no database, or no mailbox is configured. The database path never
calls them: there, a clock jump moves the case clock and the job runner fires what is due.
"""

from __future__ import annotations

import logging
from typing import Any

from app.contracts import SendRequest
from app.story import mail_ready
from app.web.state import PROVIDERS, CaseBoard, SurfaceState, TimelineEvent, case_time_label

logger = logging.getLogger(__name__)

FOLLOWUP_REF = "AW-1042-FL1"
FOLLOWUP_TEXT = (
    "Following up on membership FL-5531. Please confirm the cancellation in writing.\n\n"
    f"Ref {FOLLOWUP_REF}"
)


async def simulate_followup(app: Any, surface: SurfaceState, board: CaseBoard) -> None:
    """In-memory +14 day jump: one follow-up into the demo mailbox, and a Sent check."""
    already = [
        record
        for record in surface.mailbox.sent
        if "FL-5531" in record.text or "following up" in record.text.casefold()
    ]
    if not already:
        profile = PROVIDERS["fitlife"]
        await surface.mailbox.send(
            SendRequest(
                mailbox="family@demo.example",
                to_addrs=[profile["recipient"]],
                subject=profile["subject"],
                text=FOLLOWUP_TEXT,
                footer_ref=FOLLOWUP_REF,
                from_name="Afterward",
            )
        )
    await _relay_and_reconcile(app, surface, board)


async def _relay_and_reconcile(app: Any, surface: SurfaceState, board: CaseBoard) -> None:
    if any(event.text.startswith("FitLife follow-up sent") for event in board.events):
        return
    sent = await relay_family_mail(app, PROVIDERS["fitlife"]["subject"], FOLLOWUP_TEXT)
    if sent:
        board.events.append(
            TimelineEvent(
                "FitLife follow-up sent through the connected mailbox.",
                case_time_label(surface, board),
                "unverified",
                "system",
            )
        )
    found = await find_sent(app, surface, FOLLOWUP_REF, live=sent)
    board.delivery = "reconciled" if found else "uncertain"
    if found:
        board.events.append(
            TimelineEvent(
                "Checked the Sent folder before saying so: the FitLife follow-up is there.",
                case_time_label(surface, board),
                "unverified",
                "system",
            )
        )


async def find_sent(app: Any, surface: SurfaceState, footer: str, *, live: bool) -> bool:
    """Look for the footer in Sent before saying a follow-up went."""
    if not live:
        return await surface.mailbox.search_sent("family@demo.example", footer) is not None
    settings = app.state.settings
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "family")
        return await mailbox.search_sent(settings.family_mailbox, footer) is not None
    except Exception:
        logger.info("sent search", extra={"kind": "mail.reconcile", "ok": False})
        return False


async def relay_family_mail(app: Any, subject: str, body: str) -> bool:
    settings = getattr(app.state, "settings", None)
    if settings is None or not mail_ready(settings):
        return False
    from app.integrations.google import gmail_mailbox_for

    try:
        mailbox = gmail_mailbox_for(settings, "family")
        await mailbox.send(
            SendRequest(
                mailbox=settings.family_mailbox,
                to_addrs=[settings.providers_mailbox],
                subject=subject,
                text=body,
                footer_ref=FOLLOWUP_REF,
                from_name="Afterward",
            )
        )
    except Exception:
        logger.info("family mail", extra={"kind": "mail.relay", "ok": False})
        return False
    return True
