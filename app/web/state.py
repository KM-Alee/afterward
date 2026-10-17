"""In-memory demo case for the desk, family view and provider console."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.call.acceptance import CallRoom
from app.fakes import FakeCallSession, FakeClock, FakeMailbox
from app.web.live import LiveHub

DEMO_CASE_ID = UUID("00000000-0000-4000-8000-0000000000d1")
EMPTY_CASE_ID = UUID("00000000-0000-4000-8000-0000000000e1")

PROVIDERS: dict[str, dict[str, str]] = {
    "northline": {
        "name": "Northline Mobile",
        "recipient": "bereavement@northline.example",
        "subject": "Line ending 4417",
    },
    "citypower": {
        "name": "City Power",
        "recipient": "accounts@citypower.example",
        "subject": "Account CP-77120",
    },
    "streambox": {
        "name": "StreamBox",
        "recipient": "help@streambox.example",
        "subject": "Subscription SB-88213",
    },
    "fitlife": {
        "name": "FitLife Gym",
        "recipient": "members@fitlife.example",
        "subject": "Membership FL-5531",
    },
    "crescent": {
        "name": "Crescent Bank",
        "recipient": "bereavement@crescentbank.example",
        "subject": "Account ending 0932",
    },
}

VARIANTS: dict[str, dict[str, str]] = {
    "nl_contradictory": {
        "provider": "northline",
        "label": "Done, but changed",
        "text": (
            "Request complete. Line transferred to Mrs Malik on a new 24-month plan. "
            "Voicemail will be reset during migration."
        ),
    },
    "nl_ack": {
        "provider": "northline",
        "label": "Received it",
        "text": "We received your request and will reply when we have looked at it.",
    },
    "nl_written": {
        "provider": "northline",
        "label": "Confirmed in writing",
        "text": (
            "Transferred to Amina Malik. The number and the existing voicemail have been kept. "
            "12 months at $30 per month."
        ),
    },
    "cp_april_feb": {
        "provider": "citypower",
        "label": "February bill",
        "text": "Please pay the April invoice. It covers February service.",
    },
    "fl_ack": {
        "provider": "fitlife",
        "label": "Received it",
        "text": "We received your cancellation request.",
    },
}

FOOTER_REF = "Ref AW-DEMO"


@dataclass
class Dim:
    kind: str
    text: str


@dataclass
class Check:
    label: str
    chip_kind: str
    chip_text: str
    why: str = ""


@dataclass
class AccountTile:
    id: str
    name: str
    label: str
    origin: str
    bucket_kind: str
    bucket_text: str
    service: Dim
    money: Dim
    docs: Dim
    next_owner: str
    next_action: str
    focus: bool = False
    conditions: list[Check] = field(default_factory=list)
    origin_detail: str = ""
    track: str = ""
    plan_line: str = ""
    commitments: list[Check] = field(default_factory=list)


@dataclass
class TimelineEvent:
    text: str
    at: str
    evidence: str
    tone: str
    quote: str = ""


@dataclass
class OutcomePanel:
    title: str
    plan_version: int
    requested: str
    requested_conditions: list[str]
    quote: str
    quote_evidence: str
    quote_at: str
    verdict_kind: str
    verdict_text: str
    checks: list[Check]
    provider: str = "Northline"


@dataclass
class FinishLine:
    kind: str
    text: str
    name: str


@dataclass
class ScheduledJob:
    label: str
    due: str
    status: str


@dataclass
class CoverageView:
    searched: list[str] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)
    not_searched: list[str] = field(default_factory=list)
    needs_you: list[str] = field(default_factory=list)
    where_else: list[str] = field(default_factory=list)


@dataclass
class ClockCase:
    """Demo clock carrier. `FakeClock.case_now` reads `clock_offset_s`."""

    clock_offset_s: int = 0
    is_demo: bool = True


@dataclass
class ProviderThread:
    provider: str
    subject: str
    request_body: str
    replies: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CaseBoard:
    id: UUID
    deceased: str
    died: str
    handler: str
    empty: bool
    is_demo: bool
    clock_case: ClockCase
    monitoring: str
    delivery: str
    accounts: list[AccountTile]
    outcome: OutcomePanel | None
    events: list[TimelineEvent]
    threads: dict[str, ProviderThread]
    family_choice: str | None = None
    source: str = "memory"
    source_label: str = "Demo data (not from the database)"
    case_time: str = ""
    outcome_simulated: bool = False
    finish_lead: str = ""
    finish_note: str = ""
    finish_lines: list[FinishLine] = field(default_factory=list)
    coverage: CoverageView = field(default_factory=CoverageView)
    scheduled: list[ScheduledJob] = field(default_factory=list)


@dataclass
class SurfaceState:
    """Process-local pages. The lead mounts this in Phase 3."""

    demo_passcode: str
    phone_calls_enabled: bool = False
    sessions: set[str] = field(default_factory=set)
    mailbox: FakeMailbox = field(default_factory=FakeMailbox)
    clock: FakeClock = field(
        default_factory=lambda: FakeClock(datetime(2026, 3, 6, 9, 0, tzinfo=UTC))
    )
    live: LiveHub = field(default_factory=LiveHub)
    cases: dict[UUID, CaseBoard] = field(default_factory=dict)
    family_tokens: dict[str, UUID] = field(default_factory=dict)
    provider_tokens: dict[str, UUID] = field(default_factory=dict)
    call_tokens: dict[str, UUID] = field(default_factory=dict)
    calls: dict[str, CallRoom] = field(default_factory=dict)
    proof_history: list[dict[str, object]] = field(default_factory=list)
    session_factory: object | None = None

    @property
    def demo_case_id(self) -> UUID:
        return DEMO_CASE_ID

    @property
    def empty_case_id(self) -> UUID:
        return EMPTY_CASE_ID


def case_time_label(surface: SurfaceState, board: CaseBoard) -> str:
    moment = surface.clock.case_now(board.clock_case)
    return f"{moment.day} {moment.strftime('%b %Y, %H:%M')} UTC"


def build_surface(demo_passcode: str, *, phone_calls_enabled: bool = False) -> SurfaceState:
    """Demo Malik snapshot plus an empty case. Tokens are generated, not stored in source."""
    surface = SurfaceState(demo_passcode=demo_passcode, phone_calls_enabled=phone_calls_enabled)
    demo = _demo_board()
    empty = _empty_board()
    surface.cases[demo.id] = demo
    surface.cases[empty.id] = empty
    family = secrets.token_urlsafe(18)
    provider = secrets.token_urlsafe(18)
    call = secrets.token_urlsafe(18)
    empty_family = secrets.token_urlsafe(18)
    empty_provider = secrets.token_urlsafe(18)
    empty_call = secrets.token_urlsafe(18)
    surface.family_tokens[family] = demo.id
    surface.provider_tokens[provider] = demo.id
    surface.call_tokens[call] = demo.id
    surface.family_tokens[empty_family] = empty.id
    surface.provider_tokens[empty_provider] = empty.id
    surface.call_tokens[empty_call] = empty.id
    surface.calls[call] = CallRoom(session=FakeCallSession(), status="ready")
    surface.calls[empty_call] = CallRoom(session=FakeCallSession(), status="none")
    attach_call_rooms(surface)
    return surface


def attach_call_rooms(surface: SurfaceState) -> None:
    """Give each call room the approved plan's request text (from the rows, when there is a DB)."""
    from app.web.plan_text import attach_request_provider

    for token, room in surface.calls.items():
        case_id = surface.call_tokens.get(token)
        if case_id is not None:
            attach_request_provider(surface, room, case_id)


def _demo_board() -> CaseBoard:
    quote = (
        "Request complete. Line transferred to Mrs Malik on a new 24-month plan. "
        "Voicemail will be reset during migration."
    )
    northline_checks = [
        Check("Moved to Amina", "holding", "Holding", "The reply names Mrs Malik."),
        Check(
            "Voicemail kept",
            "violated",
            "Broken",
            "The reply says the voicemail will be reset.",
        ),
        Check(
            "No new contract",
            "unauthorised",
            "Not approved",
            "A 24-month plan was not in the plan.",
        ),
        Check("Number kept", "unknown", "Not stated", "The reply does not mention the number."),
    ]
    accounts = [
        AccountTile(
            "nl4417",
            "Northline Mobile",
            "Mobile line ending 4417",
            "Forward",
            "decision",
            "Needs family",
            Dim("review", "Reported transferred: not accepted"),
            Dim("unauthorised", "Unapproved 24-month plan"),
            Dim("info", "Sent: death certificate (photo)"),
            "Family",
            "Decide: correction, call, or accept",
            True,
            northline_checks,
        ),
        AccountTile(
            "nl2290",
            "Northline Mobile",
            "Mobile line ending 2290",
            "Photo",
            "unconfirmed",
            "Unconfirmed",
            Dim("neutral", "Not started"),
            Dim("neutral", "No money tracked"),
            Dim("neutral", "None needed yet"),
            "Sara",
            "Say whose line this is",
            False,
        ),
        AccountTile(
            "cb0932",
            "Crescent Bank",
            "Current account ending 0932",
            "Forward",
            "kept",
            "Kept",
            Dim("neutral", "Left open"),
            Dim("neutral", "No money tracked"),
            Dim("review", "Certified copy would be needed"),
            "—",
            "Nothing to do",
            False,
        ),
        AccountTile(
            "cp77120",
            "City Power",
            "Electricity, 14 Orchard Row",
            "Photo",
            "waiting",
            "In progress",
            Dim("progress", "Closure requested"),
            Dim("review", "February bill needs review"),
            Dim("neutral", "None required"),
            "City Power",
            "Reply to the closure request",
            False,
        ),
        AccountTile(
            "sb",
            "StreamBox",
            "Streaming subscription",
            "Forward",
            "waiting",
            "In progress",
            Dim("progress", "Cancellation requested"),
            Dim("neutral", "No money tracked"),
            Dim("neutral", "None required"),
            "StreamBox",
            "Confirm cancellation in writing",
            False,
        ),
        AccountTile(
            "fl5531",
            "FitLife Gym",
            "Membership FL-5531",
            "Forward",
            "promised",
            "Promised",
            Dim("waiting", "Cancellation acknowledged"),
            Dim("neutral", "No money tracked"),
            Dim("info", "Sent: death certificate (photo)"),
            "FitLife",
            "Follow up if the reply window passes",
            False,
        ),
        AccountTile(
            "hw",
            "Harbor Water",
            "Water, 14 Orchard Row",
            "Photo",
            "kept",
            "Kept",
            Dim("neutral", "Supply stays on"),
            Dim("neutral", "No money tracked"),
            Dim("neutral", "None needed"),
            "—",
            "Nothing to do",
            False,
        ),
        AccountTile(
            "ml",
            "Meridian Life",
            "Policy letter",
            "Photo",
            "unconfirmed",
            "Unconfirmed",
            Dim("unknown", "Not started"),
            Dim("neutral", "No money tracked"),
            Dim("neutral", "None needed yet"),
            "Sara",
            "Say whether this policy is his",
            False,
        ),
        AccountTile(
            "pb",
            "Paperleaf Books",
            "Book club subscription",
            "Forward",
            "handed",
            "With Sara",
            Dim("info", "Web form only"),
            Dim("neutral", "No money tracked"),
            Dim("neutral", "None required"),
            "Sara",
            "Submit the prepared cancellation",
            False,
        ),
    ]
    events = [
        TimelineEvent(
            "Sara confirmed the summary from her voice note.",
            "6 Mar 2026, 09:10 UTC",
            "family",
            "family",
        ),
        TimelineEvent(
            "Amina said she uses the 4417 line and the bank sends codes there.",
            "6 Mar 2026, 09:40 UTC",
            "family",
            "family",
            "That's my number, the bank sends my codes there, and his voice is on it.",
        ),
        TimelineEvent(
            "Sara approved the Northline request, plan v2.",
            "6 Mar 2026, 10:05 UTC",
            "family",
            "family",
        ),
        TimelineEvent(
            "Northline replied that the request was complete.",
            "6 Mar 2026, 11:20 UTC",
            "writing",
            "provider",
            quote,
        ),
        TimelineEvent(
            "Outcome check: not done. Voicemail would be reset and a new contract was added.",
            "6 Mar 2026, 11:21 UTC",
            "unverified",
            "system",
        ),
    ]
    outcome = OutcomePanel(
        title="Northline Mobile, line 4417",
        plan_version=2,
        requested=(
            "Move the line to Amina Malik, keep the number and the voicemail, "
            "and do not start a new contract."
        ),
        requested_conditions=[
            "Keep the number",
            "Keep the voicemail",
            "No new contract",
            "New holder: Amina Malik",
        ],
        quote=quote,
        quote_evidence="writing",
        quote_at="6 Mar 2026, 11:20 UTC",
        verdict_kind="notdone",
        verdict_text="Not done. Two conditions failed, and the number was not mentioned.",
        checks=northline_checks,
    )
    threads = {
        "northline": ProviderThread(
            "northline",
            "Line ending 4417",
            (
                "Please move the mobile line ending 4417 to Amina Malik. "
                "Keep the number and the existing voicemail, and do not start a new contract."
            ),
        ),
        "fitlife": ProviderThread(
            "fitlife",
            "Membership FL-5531",
            "Please cancel Yusuf Malik's membership FL-5531 and stop further payments.",
        ),
    }
    return CaseBoard(
        id=DEMO_CASE_ID,
        finish_lead='Not everything. Northline\'s "done" did not match the plan.',
        finish_note=("Confirmed, promised, blocked, handed back and unconfirmed stay separate."),
        finish_lines=[
            FinishLine("violated", "Not done", "Northline Mobile"),
            FinishLine("waiting", "Promised", "FitLife Gym"),
            FinishLine("unknown", "Unconfirmed", "A second Northline line, and Meridian Life"),
            FinishLine("info", "With Sara", "Paperleaf Books"),
        ],
        coverage=CoverageView(
            searched=["Forwarded email", "Photos of bills and letters"],
            not_searched=["Paper post", "Cash payments"],
        ),
        deceased="Yusuf Malik",
        died="3 March 2026",
        handler="Sara is handling the estate (as she has told us).",
        empty=False,
        is_demo=True,
        clock_case=ClockCase(),
        monitoring="interrupted",
        delivery="uncertain",
        accounts=accounts,
        outcome=outcome,
        events=events,
        threads=threads,
    )


def _empty_board() -> CaseBoard:
    return CaseBoard(
        id=EMPTY_CASE_ID,
        deceased="No case yet",
        died="",
        handler="",
        empty=True,
        is_demo=True,
        clock_case=ClockCase(),
        monitoring="ok",
        delivery="ok",
        accounts=[],
        outcome=None,
        events=[],
        threads={},
    )
