"""Step-driven showcase: the Malik story, run through the real engine one step at a time.

Every step calls the same functions the product uses: header-first inbox search, the discovery
tools, candidate sync, versioned plans and approvals, the durable job runner, the inbound reply
pipeline with quote verification, the outcome check and the clock. The only things simulated are
the outside world and the model: Sara's Gmail is `ShowcaseMailbox` (a FakeMailbox), the providers'
replies are typed in `showcase_data.py`, and the model readings are registered on `FakeAI`.
Each result lists what was real and what was simulated, and says so on the page.

State lives in Postgres: the seeded case, every row the steps write, and one `DeskSnapshot` row
(`showcase`) that remembers which steps ran. `reset_showcase` returns to the pre-onboarding start.
"""
# ruff: noqa: E501  (long prose strings: the words the audience reads)

from __future__ import annotations

import logging
import math
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import (
    CommitmentOut,
    DependencyOut,
    DocOut,
    Fact,
    HouseholdMemberOut,
    IntakeOut,
    QuotedStr,
    ReplyOut,
)
from app.ai.verify import (
    quote_in_text,
    strip_quoted_history,
    verify_dependency,
    verify_intake,
)
from app.call.guard import commitment_tripped
from app.contracts import ContractError, ImageInput, MailMessage, SqlEventBus
from app.conversation.dependency import dependency_messages
from app.conversation.intake import intake_messages
from app.demo import showcase_data as data
from app.discovery.agent import DiscoveryTools, run_discovery
from app.discovery.candidates import Candidate, ingest_photo, set_ownership
from app.discovery.coverage import NOT_SEARCHED
from app.discovery.directory import HANDBACK_STEPS
from app.discovery.household import HouseholdScan
from app.discovery.sync import sync_candidates, sync_locators
from app.engine.actions import reserve_action
from app.engine.clock import advance_case_clock
from app.engine.dependencies import apply_dependency, effect_for
from app.engine.errors import AlreadyDecided, CrisisPaused, DependencyRequired, StalePlan
from app.engine.jobs import case_now, enqueue, schedule_followup
from app.engine.pipeline import (
    extract_verified_reply,
    extraction_messages,
    match_document_requirement,
)
from app.engine.plans import approve, latest_plan, revise_plan
from app.engine.runner import RunContext, now_utc, register_executor, run_due_jobs
from app.engine.status import finish_summary
from app.fakes import FakeAI, FakeMailbox
from app.mail.inbound import process_inbound
from app.mail.jobs import register_mail_executors
from app.mail.outbound import execute_action
from app.models import (
    Account,
    Action,
    ActionStatus,
    Approval,
    ApprovalStatus,
    Autopilot,
    Case,
    ChannelName,
    Decision,
    DecisionStatus,
    Dependency,
    DependencyKind,
    DeskSnapshot,
    DiscoverySource,
    DocsStatus,
    Event,
    Job,
    JobStatus,
    Member,
    MemberRole,
    Message,
    MessageDirection,
    MoneyItem,
    Monitoring,
    OutcomeCheck,
    Ownership,
    Plan,
    PlanAction,
    ProviderProfile,
    RecipientCheck,
    ServiceStatus,
)

logger = logging.getLogger(__name__)

SNAPSHOT_ID = "showcase"
SARA = "Sara Malik"
AMINA = "Amina Malik"
SessionFactory = Callable[[], AbstractContextManager[Session]]
_BUSINESS_ACCOUNTS = ("4417", "SB-88213", "FL-5531", "CP-77120")


class ShowcaseError(Exception):
    """A step cannot run. The message is a short rule, safe to show."""


# --------------------------------------------------------------------------------------
# Environment: the simulated outside world
# --------------------------------------------------------------------------------------
class ShowcaseMailbox(FakeMailbox):
    """A FakeMailbox whose header search also returns dates, like Gmail's metadata call."""

    async def search_headers(self, mailbox: str, query: str, limit: int) -> list[dict[str, str]]:
        rows = await super().search_headers(mailbox, query, limit)
        for row in rows:
            message = self._messages[(mailbox, row["id"])]
            row["date"] = message.received_at.strftime("%-d %b %Y")
        return rows


@dataclass
class ShowcaseEnv:
    """In-process doubles. The database is the source of truth; this only holds the fakes."""

    mailbox: ShowcaseMailbox = field(default_factory=ShowcaseMailbox)
    ai: FakeAI = field(default_factory=FakeAI)
    chat: list[str] = field(default_factory=list)
    # Typed-in moments from the guided tour, and the result cards they produce.
    live: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for message in data.household_inbox():
            self.mailbox.inject(message)

    def run_context(self) -> RunContext:
        async def notify(text: str) -> bool:
            self.chat.append(f"Telegram to Sara (simulated): {text}")
            return True

        async def ask(text: str, buttons: list[tuple[str, str]]) -> bool:
            labels = " | ".join(label for _id, label in buttons)
            self.chat.append(f"Telegram to Sara (simulated): {text} [{labels}]")
            return True

        return RunContext(
            settings=SimpleNamespace(family_mailbox=data.CASE_MAILBOX),
            mailbox=self.mailbox,
            ai=self.ai,
            notify=notify,
            ask=ask,
        )


@dataclass
class StepResult:
    """What a step did. `real` and `simulated` are shown on the page, side by side."""

    step_id: str
    title: str
    headline: str
    details: list[str] = field(default_factory=list)
    real: list[str] = field(default_factory=list)
    simulated: list[str] = field(default_factory=list)
    chat: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # desk, family, onboarding, call, provider
    ran_at: str = ""


@dataclass(frozen=True)
class Step:
    """One ordered showcase step."""

    id: str
    title: str
    blurb: str
    run: Callable[[SessionFactory, ShowcaseEnv, UUID], Awaitable[StepResult]]


# --------------------------------------------------------------------------------------
# Seeding and progress
# --------------------------------------------------------------------------------------
def seed_showcase_start(session: Session) -> Case:
    """Pre-onboarding state only: the case, the two family members, declared providers and the
    inbox source Sara has granted but nothing has searched yet. No accounts, plans or mail."""
    case = Case(
        ref=data.CASE_REF,
        deceased_name=data.DECEASED,
        date_of_death=None,
        intent_text="",
        intent={},
        is_demo=True,
    )
    session.add(case)
    session.flush()
    session.add_all(
        [
            Member(
                case_id=case.id,
                name=SARA,
                role=MemberRole.owner,
                channel=ChannelName.telegram,
                stated_role_text="",
                consent={"status": "pending"},
            ),
            Member(
                case_id=case.id,
                name=AMINA,
                role=MemberRole.household,
                channel=ChannelName.telegram,
                stated_role_text="his wife; lives in the family home",
                consent={"status": "pending"},
            ),
        ]
    )
    for row in data.PROVIDERS:
        session.add(
            ProviderProfile(
                name=row["name"],
                accepted_channels=list(row["accepted_channels"]),
                required_info=list(row["required_info"]),
                required_docs=list(row["required_docs"]),
                response_window_bd=int(row["response_window_bd"]),
                completion_evidence=list(row["completion_evidence"]),
                approved_recipients=[row["approved_address"]],
                is_demo=True,
                source_url=row["source_url"],
                checked_at=datetime(2026, 10, 16, tzinfo=UTC),
            )
        )
    session.add(
        DiscoverySource(
            case_id=case.id,
            kind="household_inbox",
            started_by=SARA,
            scope_text="Sara's household inbox, read-only, headers first",
            status="waiting",
        )
    )
    session.flush()
    return case


def reset_showcase(session: Session) -> UUID:
    """Delete the demo case and its demo profiles, then seed the pre-onboarding start."""
    existing = session.scalar(select(Case).where(Case.ref == data.CASE_REF))
    if existing is not None:
        if not existing.is_demo:
            raise PermissionError("not a demo case")
        session.delete(existing)
        session.flush()
    for profile in session.scalars(
        select(ProviderProfile).where(ProviderProfile.is_demo.is_(True))
    ):
        session.delete(profile)
    session.flush()
    case = seed_showcase_start(session)
    _save_progress(session, case.id, [])
    clear_tour_live(session)
    return case.id


def _save_progress(session: Session, case_id: UUID, steps: list[dict[str, Any]]) -> None:
    payload = {"case_id": str(case_id), "steps": steps}
    row = session.get(DeskSnapshot, SNAPSHOT_ID)
    if row is None:
        session.add(DeskSnapshot(id=SNAPSHOT_ID, payload=payload))
    else:
        row.payload = payload
    session.flush()


def showcase_case(session: Session) -> Case | None:
    """The demo case, only when its progress snapshot belongs to it."""
    case = session.scalar(select(Case).where(Case.ref == data.CASE_REF, Case.is_demo.is_(True)))
    row = session.get(DeskSnapshot, SNAPSHOT_ID)
    if case is None or row is None or row.payload.get("case_id") != str(case.id):
        return None
    return case


def is_showcase_case(session: Session, case: Case) -> bool:
    """True when this case is the one the showcase is driving (used to keep other seeds away)."""
    row = session.get(DeskSnapshot, SNAPSHOT_ID)
    return row is not None and (row.payload or {}).get("case_id") == str(case.id)


def progress(session: Session) -> list[dict[str, Any]]:
    """The completed steps for the current showcase case, in order."""
    case = showcase_case(session)
    row = session.get(DeskSnapshot, SNAPSHOT_ID)
    if case is None or row is None:
        return []
    return list(row.payload.get("steps") or [])


def _record(session: Session, case_id: UUID, result: StepResult) -> None:
    result.ran_at = datetime.now(UTC).strftime("%H:%M:%S UTC")
    row = session.get(DeskSnapshot, SNAPSHOT_ID)
    steps = [
        s for s in (row.payload.get("steps") if row else []) or [] if s["step_id"] != result.step_id
    ]
    steps.append(asdict(result))
    order = {step.id: index for index, step in enumerate(STEPS)}
    steps.sort(key=lambda item: order.get(item["step_id"], 99))
    _save_progress(session, case_id, steps)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _case(session: Session, case_id: UUID) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise ShowcaseError("The showcase case is missing. Reset the showcase.")
    return case


def _accounts(session: Session, case_id: UUID) -> dict[str, Account]:
    return {
        a.account_ref: a for a in session.scalars(select(Account).where(Account.case_id == case_id))
    }


def _need(accounts: dict[str, Account], ref: str) -> Account:
    account = accounts.get(ref)
    if account is None:
        raise ShowcaseError(f"Account {ref} is not on the case yet. Run the earlier steps first.")
    return account


def _member(session: Session, case_id: UUID, name: str) -> Member:
    member = session.scalar(select(Member).where(Member.case_id == case_id, Member.name == name))
    if member is None:
        raise ShowcaseError("A family member is missing. Reset the showcase.")
    return member


def _event(session: Session, case_id: UUID, kind: str, actor: str, **payload: object) -> None:
    session.add(Event(case_id=case_id, kind=kind, actor=actor, payload=dict(payload)))


def _profile(session: Session, account: Account) -> ProviderProfile | None:
    return session.get(ProviderProfile, account.provider_id) if account.provider_id else None


def _short_hash(value: str) -> str:
    return value[:10]


def _sorted_refs(refs: set[str]) -> list[str]:
    return sorted(refs)


# --------------------------------------------------------------------------------------
# 1. Intent
# --------------------------------------------------------------------------------------
def _recorded_intake() -> IntakeOut:
    """The recorded reading of Sara's scripted voice note (used when no live model is available)."""
    return IntakeOut(
        deceased_name=QuotedStr(value="Yusuf Malik", quote="My father, Yusuf Malik"),
        date_of_death=QuotedStr(value="2026-03-03", quote="died on the third of March"),
        speaker_name=QuotedStr(value="Sara", quote="I'm Sara"),
        stated_role=QuotedStr(
            value="his daughter; handling things for the family",
            quote="I'm Sara, his daughter, and I'm handling things for the family",
        ),
        household_members=[
            HouseholdMemberOut(name=None, relationship="mother", quote="Mum's phone"),
            HouseholdMemberOut(name=None, relationship="a guess", quote="never said this"),
        ],
        intent_keep=[
            QuotedStr(value="Mum's phone", quote="keep Mum's phone"),
            QuotedStr(value="Dad's voicemail", quote="keep Dad's voicemail"),
        ],
        intent_stop=[
            QuotedStr(value="Bills that don't matter", quote="stop the bills that don't matter")
        ],
        intent_protect=[
            QuotedStr(value="His voice on the voicemail", quote="His voice is on it"),
            QuotedStr(value="A claim nobody made", quote="the house must be sold"),
        ],
        missing_fields=[],
    )


def _parse_date(value: str | None):
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def _qs(item: QuotedStr) -> dict[str, str] | None:
    return {"value": item.value, "quote": item.quote} if item.value else None


def _qlist(items: list[QuotedStr]) -> list[dict[str, str]]:
    return [row for row in (_qs(i) for i in items) if row]


async def step_intent(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Sara's voice note: every fact is kept only if its quote is really in the transcript."""
    live = env.live.get("intake")
    if live:
        transcript, reading = str(live["text"]), live["reading"]
    else:
        transcript, reading = data.SARA_TRANSCRIPT, _recorded_intake()
    verified = verify_intake(reading, transcript)
    dropped = (
        (len(reading.household_members) - len(verified.household_members))
        + (len(reading.intent_keep) - len(verified.intent_keep))
        + (len(reading.intent_stop) - len(verified.intent_stop))
        + (len(reading.intent_protect) - len(verified.intent_protect))
    )
    died = _parse_date(verified.date_of_death.value)
    env.live["intake_card"] = {
        "deceased": _qs(verified.deceased_name),
        "died": _qs(verified.date_of_death),
        "role": _qs(verified.stated_role),
        "keep": _qlist(verified.intent_keep),
        "stop": _qlist(verified.intent_stop),
        "protect": _qlist(verified.intent_protect),
        "dropped": dropped,
        "date_kept_on_file": died is None,
    }
    with factory() as session:
        case = _case(session, case_id)
        sara = _member(session, case.id, SARA)
        # Code decides: a date the words do not support never changes the case; the file date stays.
        case.date_of_death = died or data.DATE_OF_DEATH
        keep = [q.value for q in verified.intent_keep if q.value]
        stop = [q.value for q in verified.intent_stop if q.value]
        protect = [q.value for q in verified.intent_protect if q.value]
        case.intent = {"keep": keep, "stop": stop, "protect": protect}
        case.intent_text = (
            "Stop "
            + (", ".join(s.lower() for s in stop) or "nothing stated")
            + "; keep "
            + (" and ".join(keep) or "nothing stated")
            + "."
        )
        sara.stated_role_text = verified.stated_role.value or ""
        sara.consent = {
            "status": "granted",
            "via": "Telegram (simulated)",
            "at": now_utc().isoformat(),
        }
        _event(session, case.id, "intent.captured", "Sara", facts=5, dropped=dropped)
        session.commit()
    model_live = bool(live) and live.get("source") == "live"
    chat = [
        f"Sara ({'typed by the presenter' if live else 'voice note, simulated'}): {transcript}",
        "Afterward (simulated Telegram): Thank you, Sara. "
        f"Stop: {', '.join(stop) or 'nothing stated'}. Keep: {' and '.join(keep) or 'nothing stated'}. "
        "I will ask before anything is sent. Is that right?",
    ]
    return StepResult(
        step_id="intent",
        title="Sara states it once",
        headline=f"Intent captured once; {dropped} unsupported claims dropped for lacking a quote",
        details=[
            f"Kept: {', '.join(keep)}. Stopped: {', '.join(stop)}. Protected: {', '.join(protect)}.",
            "Her role is recorded as stated by her, never as 'executor'.",
            f"{dropped} readings the model offered had no matching words in what was said and were removed."
            if dropped
            else "Every fact kept has a quote that appears in what was said.",
        ],
        real=[
            "verify_intake drops every fact whose quote is not in the transcript",
            "Case date of death, intent and consent are written to Postgres",
            *(
                ["A live model read the words that were typed or spoken (intake role)"]
                if model_live
                else []
            ),
        ],
        simulated=[
            (
                "The words were typed or spoken by the presenter; the reading is "
                + ("live" if model_live else "recorded model output")
                if live
                else "The voice note, its transcription and the intake reading are scripted (no model call)"
            ),
            "Telegram is not connected; the chat lines are a labelled log",
        ],
        chat=chat,
        links=["family"],
    )


# --------------------------------------------------------------------------------------
# 2. Discover
# --------------------------------------------------------------------------------------
async def step_discover(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Headers first, Sara ticks, the discovery tools read and propose, then candidates sync."""
    scan = HouseholdScan(
        client=env.mailbox,
        mailbox=data.HOUSEHOLD_MAILBOX,
        owner=SARA,
        names=(data.DECEASED,),
        address=data.ADDRESS,
    )
    candidates: list[Candidate] = []
    tools = DiscoveryTools(candidates=candidates, scan=scan, ai=env.ai)
    await tools.search_inbox_headers()
    listed = scan.listing()
    tools.ask_to_read([h.id for h in listed if h.id in data.TICKED_IDS], "These look like bills")
    ticked = scan.tick(list(data.TICKED_IDS), by=SARA)  # the family chooses; the agent cannot
    by_mail = {meta["mail_id"]: ref for ref, meta in data.ACCOUNTS.items() if "mail_id" in meta}
    proposed: list[str] = []
    for message_id in ticked:
        raw = await tools.read_message(message_id)
        ref = by_mail.get(message_id)
        text = raw if ref and ref in raw else ""
        if not ref or not text:
            continue  # the reading found no account reference in the text
        meta = data.ACCOUNTS[ref]
        header = scan.headers[message_id]
        tools.propose_candidate(meta["provider"], ref, f"inbox:{message_id}", meta["label"])
        candidate = next(c for c in candidates if c.account_ref == ref)
        candidate.holder_name = meta["holder"]
        candidate.origin = "household inbox"
        candidate.evidence = f"“{header.subject}” from {header.sender}, {header.date}"
        proposed.append(ref)
    # Photos Sara sent. The reading is registered on FakeAI; a phone photo is forced to `photo`.
    for ref, meta in data.ACCOUNTS.items():
        if meta["via"] != "photo":
            continue
        label = meta["photo"]
        payload = {
            "doc_type": "",
            "form": "photo",
            "date_of_death": None,
            "certificate_number": None,
        }
        payload.update(data.PHOTO_DOCS[ref])
        from app.discovery.candidates import photo_messages

        env.ai.register_structured(
            "document_reader",
            DocOut,
            photo_messages(label),
            DocOut.model_validate(payload),
            images=[ImageInput(data=data.PHOTO_BYTES[ref], mime="image/jpeg")],
        )
        await ingest_photo(
            env.ai,
            data.PHOTO_BYTES[ref],
            "image/jpeg",
            label,
            candidates,
            evidence=f"photo: {label}",
        )
        candidate = next(c for c in candidates if c.account_ref == ref)
        candidate.service_label = meta["label"]
        candidate.holder_name = meta["holder"]
        proposed.append(ref)
    suggestions = await run_discovery(tools, None)
    with factory() as session:
        case = _case(session, case_id)
        created = sync_candidates(session, case.id, candidates)
        accounts = _accounts(session, case.id)
        for ref, meta in data.ACCOUNTS.items():
            account = accounts.get(ref)
            if account is not None:
                account.origin_evidence = account.origin_evidence.removeprefix("Household inbox: ")
            if (
                account is not None
                and meta.get("note")
                and meta["note"] not in account.origin_evidence
            ):
                account.origin_evidence = f"{account.origin_evidence}; {meta['note']}"
        source = session.scalar(
            select(DiscoverySource).where(
                DiscoverySource.case_id == case.id, DiscoverySource.kind == "household_inbox"
            )
        )
        if source is not None:
            source.status = "searched"
            source.matched = len(scan.headers)
            source.read = len(scan.read)
        _event(
            session,
            case.id,
            "discovery.searched",
            "Afterward",
            headers=len(scan.headers),
            read=len(scan.read),
            accounts=len(accounts),
        )
        session.commit()
    unread = [h for h in listed if h.id not in scan.read]
    return (
        StepResult(
            step_id="discover",
            title="Find candidate accounts",
            headline=(
                f"{len(candidates)} candidate accounts found from {len(listed)} inbox headers and "
                f"{len(data.PHOTO_BYTES)} photos; nothing is called 'his' yet"
            ),
            details=[
                f"Header search listed {len(listed)} messages; Sara ticked {len(ticked)}, so "
                f"{len(unread)} were never read: "
                + "; ".join(f"“{h.subject}”" for h in unread)
                + ".",
                f"Query built by code from the case: {scan.last_query}",
                "Candidates are all 'Unconfirmed' until the family says so.",
                *[f"Suggestion: {s.text}" for s in suggestions[:3]],
                "Not searched, by design: " + "; ".join(NOT_SEARCHED[:2]) + ".",
            ],
            real=[
                "HouseholdScan builds the query, lists headers only and refuses unticked reads",
                "DiscoveryTools: read_message, propose_candidate; the agent cannot confirm or add a recipient",
                "sync_candidates writes the account rows; coverage counts come from the database",
            ],
            simulated=[
                "Sara's Gmail is an in-memory FakeMailbox with 8 invented messages",
                "The photo readings are registered on FakeAI; the inbox reading is a scripted agent (no model call)",
            ],
            links=["onboarding", "desk"],
        )
        if created
        else StepResult(
            step_id="discover",
            title="Find candidate accounts",
            headline="Candidates were already on the case; nothing new was added",
            real=["sync_candidates is idempotent"],
            links=["onboarding"],
        )
    )


# --------------------------------------------------------------------------------------
# 3. Confirm
# --------------------------------------------------------------------------------------
_DECISIONS: dict[str, tuple[str, str]] = {
    "4417": ("confirmed", "Sara: his line."),
    "SB-88213": ("confirmed", "Sara: his subscription."),
    "FL-5531": ("confirmed", "Sara: his membership."),
    "CP-77120": ("confirmed", "Sara: the house electricity, in his name."),
    "HW-20418": ("confirmed", "Sara: the house water, in his name."),
    "PB-3017": ("confirmed", "Sara: his book club."),
    "2290": ("removed", "Sara: that is Mum's own line on the same bill. Not his."),
    "0932": ("needs_check", "Sara: the statement shows a second holder. Shared or not sure."),
}


async def step_confirm(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Only the family's buttons change ownership. One candidate is left undecided on purpose."""
    del env
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        for ref, (choice, _why) in _DECISIONS.items():
            account = _need(accounts, ref)
            if account.ownership is not Ownership.unconfirmed:
                continue
            probe = Candidate(
                account_ref=ref,
                provider=account.service_label,
                service_label=account.service_label,
                holder_name=account.holder_name,
                origin=account.origin.value,
            )
            if not set_ownership([probe], ref, choice):
                raise ShowcaseError(f"{ref} could not be decided")
            if probe.ownership == "confirmed":
                account.ownership = Ownership.confirmed
                account.next_step = {
                    "owner": "afterward",
                    "action": "Check what depends on it, then draft a plan",
                    "provider": (account.next_step or {}).get("provider", ""),
                }
            elif probe.ownership == "removed":
                account.ownership = Ownership.not_theirs
            else:
                account.next_step = {
                    "owner": "family",
                    "action": "Check whether this is his",
                    "flag": "needs_check",
                    "provider": (account.next_step or {}).get("provider", ""),
                }
            _event(
                session,
                case.id,
                "ownership.set",
                SARA,
                account_id=str(account.id),
                choice=probe.ownership,
            )
        session.commit()
        total = len(accounts)
        confirmed = sum(1 for a in accounts.values() if a.ownership is Ownership.confirmed)
        unconfirmed = [r for r, a in accounts.items() if a.ownership is Ownership.unconfirmed]
    return StepResult(
        step_id="confirm",
        title="Family confirms whose accounts these are",
        headline=f"{confirmed} of {total} confirmed by Sara; 1 not his, 1 shared, {len(unconfirmed)} left unconfirmed",
        details=[
            "2290 was removed: it is Amina's own line on the same bill.",
            "0932 (Crescent Bank) is marked shared or not sure: no plan will be drafted until it is sorted.",
            "ML-6610 (a policy letter with a hidden name) stays Unconfirmed, and is counted that way at the end.",
        ],
        real=[
            "set_ownership: the only way a candidate becomes his is a family decision",
            "Each decision is an audit event on the case",
        ],
        simulated=["Sara's taps are scripted; on the family page she would press the buttons"],
        links=["onboarding", "desk"],
    )


# --------------------------------------------------------------------------------------
# 4. Dependency
# --------------------------------------------------------------------------------------
def _plan_conditions(effects: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [dict(c) for c in effects]


async def step_dependency(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Ask who still uses each service. Amina's answer rewrites the 4417 plan."""
    live = env.live.get("dependency")
    said = str(live["text"]) if live else data.AMINA_QUOTE
    answers = (
        [live["answer"]]
        if live
        else [DependencyOut.model_validate(r) for r in (data.AMINA_ACCESS, data.AMINA_MEMORY)]
    )
    details: list[str] = []
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        sara, amina = _member(session, case.id, SARA), _member(session, case.id, AMINA)
        northline = _need(accounts, "4417")
        profile = _profile(session, northline)
        if profile is None:
            raise ShowcaseError("Northline has no declared profile")
        recipient = str(profile.approved_recipients[0])
        docs = [{"type": "death_certificate", "form": "photo"}]
        fallback = "Ask the family before anything else is sent."
        if latest_plan(session, northline.id) is None:
            draft = revise_plan(
                session,
                case_id=case.id,
                account_id=northline.id,
                action=PlanAction.transfer,
                conditions=[],
                documents=docs,
                recipient=recipient,
                fallback=fallback,
            )
            try:
                approve(
                    session,
                    plan_id=draft.id,
                    version=draft.version,
                    plan_hash_value=draft.hash,
                    member_id=sara.id,
                )
            except DependencyRequired:
                details.append(
                    "Approving the first draft was refused: no one has said who else uses this line."
                )
        first = session.scalar(
            select(Plan).where(Plan.account_id == northline.id, Plan.version == 1)
        )
        # Amina's answer. Quotes are checked against her words; conditions come from code.
        added: list[dict[str, str]] = []
        for answer in answers:
            if not quote_in_text(answer.evidence_quote, said):
                raise ShowcaseError("Amina's quote is not in her words")
            already = session.scalar(
                select(Dependency.id).where(
                    Dependency.account_id == northline.id,
                    Dependency.statement == answer.statement,
                )
            )
            if already is None:
                apply_dependency(
                    session,
                    case_id=case.id,
                    account=northline,
                    dependency=answer,
                    source_member_id=amina.id,
                    plan=None,
                )
            added.extend(dict(c) for c in effect_for(answer).conditions)
        amina.consent = {"status": "granted", "via": "Telegram voice note (simulated)"}
        merged = _plan_conditions(list({c["key"]: c for c in added}.values()))
        revised = revise_plan(
            session,
            case_id=case.id,
            account_id=northline.id,
            action=PlanAction.transfer,
            conditions=merged,
            documents=docs,
            recipient=recipient,
            fallback=fallback,
        )
        if first is not None and revised.id != first.id:
            try:
                approve(
                    session,
                    plan_id=first.id,
                    version=first.version,
                    plan_hash_value=first.hash,
                    member_id=sara.id,
                )
            except StalePlan:
                details.append(
                    "A card built from the first draft was refused as stale; only the revised "
                    "plan can be approved."
                )
            except (AlreadyDecided, DependencyRequired):
                pass
        northline.next_step = {
            "owner": "family",
            "action": "Approve the revised plan",
            "provider": "Northline Mobile",
        }
        bank = accounts.get("0932")
        # Everyone else: one question each, answered by Sara, then a plan draft.
        for ref, statement in data.SARA_NOBODY_USES.items():
            account = _need(accounts, ref)
            exists = session.scalar(
                select(Dependency.id).where(Dependency.account_id == account.id)
            )
            if exists is None:
                session.add(
                    Dependency(
                        case_id=case.id,
                        account_id=account.id,
                        kind=DependencyKind.access,
                        statement=statement,
                        source_member_id=sara.id,
                    )
                )
            prof = _profile(session, account)
            if prof is None:
                continue
            docs_needed = [dict(d) for d in prof.required_docs if d.get("form") == "photo"]
            plan = revise_plan(
                session,
                case_id=case.id,
                account_id=account.id,
                action=PlanAction.close,
                conditions=[],
                documents=docs_needed,
                recipient=str(prof.approved_recipients[0]),
                fallback="Ask the family before anything else is sent.",
            )
            account.next_step = {
                "owner": "family",
                "action": "Approve the plan",
                "provider": prof.name,
            }
            details.append(
                f"{prof.name} {ref}: plan v{plan.version} drafted (close, no conditions)."
            )
        final = latest_plan(session, northline.id)
        assert final is not None
        link = "Crescent Bank 0932" if bank is not None else "the bank"
        _event(session, case.id, "dependency.answered", "Amina", plan_version=final.version)
        session.commit()
        conds = ", ".join(c["key"].replace("_", " ") for c in final.conditions)
    details.insert(0, f"Amina: “{said}”")
    details.insert(
        1,
        f"The 4417 plan changed from v1 (transfer, no conditions) to v{final.version}: transfer to Amina with conditions: {conds}. The access answer is linked to {link}.",
    )
    env.live["dependency_card"] = {
        "quote": said,
        "answers": [{"kind": a.kind, "statement": a.statement} for a in answers],
        "before": {"version": 1, "action": "transfer", "conditions": []},
        "after": {
            "version": final.version,
            "action": final.action.value,
            "conditions": [str(c["key"]) for c in final.conditions],
        },
        "linked": link,
    }
    return StepResult(
        step_id="dependency",
        title="Amina's answer changes the plan",
        headline=f"One answer from Amina changed 4417 from a plain transfer to plan v{final.version} with {len(final.conditions)} conditions",
        details=details,
        real=[
            "apply_dependency stores the answer and links the bank account it mentions",
            "effect_for turns the answer into plan conditions in code; the model writes none",
            "approve() refused a transfer with no dependency answer, and refused a stale plan hash",
            "revise_plan versions the plan; each version has its own hash",
        ],
        simulated=[
            (
                "Amina's words were typed or spoken by the presenter; the quote is verified against them"
                if live
                else "Amina's voice note and its reading are scripted; her quote is verified against her words"
            )
        ],
        chat=[
            "Afterward (simulated Telegram) to Amina: Does anyone still use the line ending 4417?",
            f"Amina ({'typed by the presenter' if live else 'voice note, simulated'}): {said}",
        ],
        links=["desk", "family"],
    )


# --------------------------------------------------------------------------------------
# 5. Approve
# --------------------------------------------------------------------------------------
def _request_body(case: Case, account: Account, plan: Plan, provider: str) -> str:
    verbs = {
        "transfer": "move the account to the family member named below",
        "close": "close the account",
    }
    lines = [
        f"Hello {provider},",
        "",
        f"I am writing on behalf of the family of {case.deceased_name}, who died on "
        f"{case.date_of_death:%-d %B %Y}. The family asks you to {verbs.get(plan.action.value, plan.action.value)}.",
        f"Account: {account.service_label} (reference {account.account_ref}).",
    ]
    if plan.action is PlanAction.transfer:
        lines.append("New holder: Mrs Amina Malik, his wife and the person who uses the line.")
    if plan.conditions:
        lines.append("The family's conditions:")
        for condition in plan.conditions:
            text = {
                "number_kept": "The phone number must stay the same.",
                "voicemail_preserved": "The existing voicemail greeting must be kept, not reset.",
            }.get(str(condition["key"]), str(condition["key"]).replace("_", " "))
            lines.append(f"- {text}")
        lines.append("Please do not change the contract length or price without asking the family.")
    if plan.documents_to_disclose:
        lines.append("A photo of the death certificate is available if you require it.")
    lines.append("Please reply in writing to this address with the outcome.")
    return "\n".join(lines)


async def step_approve(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Specific approval on the exact plan hash; each approval queues one send_request job."""
    del env
    summary: list[str] = []
    chat: list[str] = []
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        sara = _member(session, case.id, SARA)
        for ref in _BUSINESS_ACCOUNTS:
            account = _need(accounts, ref)
            plan = latest_plan(session, account.id)
            profile = _profile(session, account)
            if plan is None or profile is None:
                raise ShowcaseError(f"No plan for {ref}. Run the dependency step first.")
            try:
                approval = approve(
                    session,
                    plan_id=plan.id,
                    version=plan.version,
                    plan_hash_value=plan.hash,
                    member_id=sara.id,
                    card={
                        "recipient": plan.recipient,
                        "action": plan.action.value,
                        "conditions": [c["key"] for c in plan.conditions],
                        "documents": [d["type"] for d in plan.documents_to_disclose],
                    },
                )
            except AlreadyDecided:
                approval = session.scalar(
                    select(Approval).where(
                        Approval.plan_id == plan.id, Approval.status == ApprovalStatus.approved
                    )
                )
                assert approval is not None
            key = f"{ref}-v{plan.version}"
            action = reserve_action(
                session,
                case_id=case.id,
                kind="email_send",
                idem_key=f"showcase:send:{plan.id}",
                request={
                    "account_id": str(account.id),
                    "to_addrs": [plan.recipient],
                    "subject": f"{account.service_label}: request from the Malik family",
                    "body": _request_body(case, account, plan, profile.name),
                    "action_key": key,
                    "mailbox": data.CASE_MAILBOX,
                    "thread_id": f"showcase-{ref}",
                    "from_name": "Afterward (for the Malik family)",
                },
            )
            enqueue(
                session,
                case_id=case.id,
                kind="send_request",
                run_at_case_time=case_now(case, datetime.now(UTC)) - timedelta(minutes=1),
                idem_key=f"showcase:sendjob:{plan.id}",
                payload={
                    "plan_id": str(plan.id),
                    "plan_version": plan.version,
                    "plan_hash": plan.hash,
                    "approval_id": str(approval.id),
                    "action": plan.action.value,
                    "outbound": True,
                    "action_idem_key": action.idem_key,
                    "account_id": str(account.id),
                    "reason": {"type": "always"},
                },
            )
            account.next_step = {
                "owner": "afterward",
                "action": "Send the approved request",
                "provider": profile.name,
            }
            conds = ", ".join(c["key"].replace("_", " ") for c in plan.conditions) or "none"
            summary.append(
                f"{profile.name} {ref}: approved plan v{plan.version} ({plan.action.value} to "
                f"{plan.recipient}; conditions: {conds}; hash {_short_hash(plan.hash)})."
            )
            chat.append(
                f"Approval card (simulated Telegram): {plan.action.value.capitalize()} {account.service_label} "
                f"by emailing {plan.recipient}. Conditions: {conds}. Documents: "
                f"{', '.join(d['type'] for d in plan.documents_to_disclose) or 'none'}. "
                "If any of this changes, this approval is void. [Approve] [Change] [Stop]"
            )
        _event(session, case.id, "approval.granted", SARA, accounts=len(_BUSINESS_ACCOUNTS))
        session.commit()
    return StepResult(
        step_id="approve",
        title="Sara approves four specific requests",
        headline=f"{len(_BUSINESS_ACCOUNTS)} plans approved on exact hashes; {len(_BUSINESS_ACCOUNTS)} send jobs queued, none sent",
        details=summary
        + [
            "Only these four accounts have an email route and a confirmed owner. "
            "Crescent Bank (shared), Harbor Water and Paperleaf (no email route) and the unconfirmed "
            "accounts get no send.",
        ],
        real=[
            "approve() is a compare-and-set on plan id, version and hash",
            "Each approval binds one send_request job and an email action row",
            "Recipients come from the provider profile, never from mail text",
        ],
        simulated=["Sara's Approve taps are scripted; the cards are shown as a labelled chat log"],
        chat=chat,
        links=["desk"],
    )


# --------------------------------------------------------------------------------------
# 6. Autopilot
# --------------------------------------------------------------------------------------
async def step_steady(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Sara switches Autopilot to Steady: follow-ups on approved plans stop asking first."""
    del env
    with factory() as session:
        case = _case(session, case_id)
        case.autopilot = Autopilot.steady
        _event(session, case.id, "autopilot.changed", SARA, autopilot="steady")
        session.commit()
    return StepResult(
        step_id="steady",
        title="Sara switches Autopilot to Steady",
        headline="Steady: follow-ups under an approved plan run without asking; new requests still need approval",
        details=[
            "Gentle (the default) asks before each follow-up. Steady lets a follow-up run, "
            "but only inside a plan that is still approved and current.",
        ],
        real=["Case.autopilot is read again by the policy check when each job runs"],
        simulated=["Sara's tap is scripted"],
        links=["desk"],
    )


# --------------------------------------------------------------------------------------
# Job runner helper
# --------------------------------------------------------------------------------------
async def run_jobs(factory: SessionFactory, env: ShowcaseEnv, *, rounds: int = 4) -> int:
    """Run due jobs through the durable runner until a round does nothing (a follow-up queues a send)."""
    from app.engine import executors as _engine_executors  # noqa: F401  (registers kinds)

    register_mail_executors(register_executor)
    done = 0
    for _round in range(rounds):
        fired = await run_due_jobs(factory, env.run_context(), wall=now_utc())
        done += fired
        if not fired:
            break
    return done


# --------------------------------------------------------------------------------------
# 7. Send
# --------------------------------------------------------------------------------------
async def step_send(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """The runner re-checks approval and recipient, then sends through the simulated Gmail."""
    with factory() as session:
        case = _case(session, case_id)
        case.monitoring = Monitoring.ok
        session.commit()
    fired = await run_jobs(factory, env)
    sent_lines: list[str] = []
    blocked: list[str] = []
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        for ref in _BUSINESS_ACCOUNTS:
            account = _need(accounts, ref)
            plan = latest_plan(session, account.id)
            action = session.scalar(
                select(Action).where(
                    Action.case_id == case.id, Action.idem_key == f"showcase:send:{plan.id}"
                )
            )
            profile = _profile(session, account)
            if action is None or profile is None or plan is None:
                continue
            if action.status not in {ActionStatus.sent, ActionStatus.reconciled}:
                blocked.append(f"{ref}: {action.request.get('blocked', action.status.value)}")
                continue
            account.status_service = ServiceStatus.requested
            account.status_docs = (
                DocsStatus.sent if plan.documents_to_disclose else DocsStatus.none_needed
            )
            account.next_step = {
                "owner": "provider",
                "action": "Wait for the reply",
                "provider": profile.name,
            }
            approval = session.scalar(
                select(Approval).where(
                    Approval.plan_id == plan.id, Approval.status == ApprovalStatus.approved
                )
            )
            job = schedule_followup(
                session,
                case=case,
                account_id=account.id,
                plan=plan,
                approval_id=approval.id,
                sent_at=datetime.now(UTC),
                window_bd=profile.response_window_bd,
            )
            sent_lines.append(
                f"{profile.name}: sent to {plan.recipient}, ref {action.request.get('footer_ref')}; "
                f"follow-up scheduled {job.run_at_case_time:%-d %b %Y} "
                f"({profile.response_window_bd} business days)."
            )
        session.commit()
    return StepResult(
        step_id="send",
        title="The job runner sends, after checking again",
        headline=f"{len(sent_lines)} requests sent by the job runner; {len(blocked)} blocked",
        details=sent_lines
        + [f"Blocked: {b}" for b in blocked]
        + [
            "Every email carries a visible 'Ref AW-1042-…' footer and says an AI assistant wrote it."
        ],
        real=[
            f"run_due_jobs leased and ran {fired} due jobs; preflight re-checked approval, plan and mailbox",
            "send_request re-verified the recipient against the provider profile at send time",
            "The email action, outbound message and follow-up job are Postgres rows",
        ],
        simulated=["Gmail is an in-memory FakeMailbox: no email left this machine"],
        links=["desk", "provider"],
    )


# --------------------------------------------------------------------------------------
# 8. Replies
# --------------------------------------------------------------------------------------
def _register_reply(env: ShowcaseEnv, text: str, reply: ReplyOut) -> None:
    env.ai.register_structured(
        "reply_reader", ReplyOut, extraction_messages(strip_quoted_history(text)), reply
    )


def _fact(key: str, value: str, quote: str) -> Fact:
    return Fact.model_validate({"key": key, "value": value, "evidence_quote": quote})


def _commit(**kwargs: Any) -> CommitmentOut:
    base: dict[str, Any] = {
        "negated": False,
        "conditions_or_requirements": [],
        "facts": [],
        "scope": "this_service",
        "effective_date": None,
        "interpretation": "clear",
    }
    base.update(kwargs)
    return CommitmentOut.model_validate(base)


def _replies() -> list[tuple[str, str, str, str, ReplyOut]]:
    """(ref, from_addr, subject, text, reading) for the scripted provider replies."""
    northline = ReplyOut(
        commitments=[
            _commit(
                account_hint="line ending 4417",
                action="transfer",
                status="completed",
                evidence_quote="Line ending 4417 has been transferred to Mrs Amina Malik",
                facts=[
                    _fact("new_holder", "Amina Malik", "Mrs Amina Malik"),
                    _fact("contract_months", "24", "24-month plan"),
                    _fact("monthly_price", "28.00", "$28.00 per month"),
                    _fact(
                        "voicemail_preserved", "false", "Voicemail will be reset during migration"
                    ),
                ],
            )
        ],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )
    streambox = ReplyOut(
        commitments=[
            _commit(
                account_hint="SB-88213",
                action="close",
                status="completed",
                evidence_quote="Your StreamBox subscription SB-88213 has been cancelled effective "
                "17 October 2026. Cancellation confirmation SBX-CXL-550219",
                effective_date="2026-10-17",
            )
        ],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )
    citypower = ReplyOut(
        commitments=[
            _commit(
                account_hint="CP-77120",
                action="close",
                status="completed",
                evidence_quote="Account CP-77120 has been closed: closure confirmation "
                "CPW-208841, final meter read 48,213 kWh",
            ),
            _commit(
                account_hint="CP-77120",
                action="refund",
                status="completed",
                evidence_quote="A refund of $42.00 for overpayment has been issued to the card on file",
                facts=[
                    _fact(
                        "refund_amount",
                        "42.00",
                        "A refund of $42.00 for overpayment has been issued",
                    )
                ],
            ),
        ],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )
    return [
        (
            "4417",
            "bereavement@northline.example",
            "Re: Mobile line ending 4417: request from the Malik family",
            data.NORTHLINE_REPLY,
            northline,
        ),
        (
            "SB-88213",
            "help@streambox.example",
            "Re: Streaming subscription: request from the Malik family",
            data.STREAMBOX_REPLY,
            streambox,
        ),
        (
            "CP-77120",
            "accounts@citypower.example",
            "Re: Electricity, 14 Orchard Row: request from the Malik family",
            data.CITYPOWER_REPLY,
            citypower,
        ),
    ]


_CONDITION_LABELS = {
    "number_kept": "The number stays the same",
    "voicemail_preserved": "The voicemail is kept",
    "contract_months": "No longer contract",
    "monthly_price": "Price unchanged",
    "new_holder": "New holder is Amina",
    "new_contract": "A new contract",
    "price_change": "A different price",
}
_EXTRA_FACT = {"new_contract": "contract_months", "price_change": "monthly_price"}


def _reply_card(check: OutcomeCheck, reading: ReplyOut) -> dict[str, Any]:
    """One row per plan condition: what the reply says about it, with the supporting quote."""
    quotes: dict[str, str] = {}
    for commitment in reading.commitments:
        for fact in commitment.facts:
            quotes.setdefault(fact.key, fact.evidence_quote)
    state_of = {"matched": "Holding", "violated": "Broken", "missing": "Not stated"}
    rows: list[dict[str, str]] = []
    action_quote = next((c.evidence_quote for c in reading.commitments), "")
    action_state = str(check.results.get("action", "missing"))
    rows.append(
        {
            "key": "action",
            "label": "The transfer itself",
            "state": {"completed": "Holding"}.get(action_state, "Not stated"),
            "quote": action_quote if action_state != "missing" else "",
        }
    )
    for key, value in check.results.items():
        if key in {"action", "unauthorised"}:
            continue
        rows.append(
            {
                "key": key,
                "label": _CONDITION_LABELS.get(key, key.replace("_", " ").capitalize()),
                "state": state_of.get(str(value), "Not stated"),
                "quote": quotes.get(key, "") if value != "missing" else "",
            }
        )
    for key in check.results.get("unauthorised") or []:
        rows.append(
            {
                "key": str(key),
                "label": _CONDITION_LABELS.get(str(key), str(key).replace("_", " ").capitalize())
                + " (not in the plan)",
                "state": "Not approved",
                "quote": quotes.get(_EXTRA_FACT.get(str(key), str(key)), ""),
            }
        )
    verdict = {"resolved": "Done, with evidence", "open": "Not done yet"}.get(
        check.verdict, "Not done: needs the family's decision"
    )
    return {"verdict": verdict, "kind": check.verdict, "rows": rows}


async def step_reply(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Replies arrive through the polling path. Each is checked against the approved plan."""
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        threads: dict[str, str] = {}
        for ref in ("4417", "SB-88213", "CP-77120"):
            account = _need(accounts, ref)
            action = session.scalar(
                select(Action).where(
                    Action.case_id == case.id,
                    Action.idem_key.like("showcase:send:%"),
                    Action.request["account_id"].astext == str(account.id),
                )
            )
            if action is None or action.status is not ActionStatus.sent:
                raise ShowcaseError(f"{ref} was not sent yet. Run the send step first.")
            threads[ref] = str(action.request.get("thread_id"))
    base = datetime.now(UTC)
    rows = _replies()
    override = env.live.get("reply")
    if override:  # the presenter played Northline: their words and their reading replace the script
        rows = [
            (r[0], r[1], r[2], str(override["text"]), override["reading"]) if r[0] == "4417" else r
            for r in rows
        ]
    northline_reading = next(r[4] for r in rows if r[0] == "4417")
    for index, (ref, sender, subject, text, reading) in enumerate(
        sorted(rows, key=lambda row: row[0] == "4417")
    ):
        _register_reply(env, text, reading)
        env.mailbox.inject(
            MailMessage(
                mailbox=data.CASE_MAILBOX,
                gmail_id=f"showcase-reply-{ref}",
                thread_id=threads[ref],
                rfc_message_id=f"<reply-{ref}@provider.example>",
                from_addr=sender,
                to_addrs=[data.CASE_MAILBOX],
                subject=subject,
                latest_text=strip_quoted_history(text),
                full_text=text,
                received_at=base + timedelta(minutes=index + 1),
            )
        )
    env.mailbox.inject(
        MailMessage(
            mailbox=data.CASE_MAILBOX,
            gmail_id="showcase-reply-spoof",
            thread_id="",
            rfc_message_id="<spoof@elsewhere.example>",
            from_addr=data.SPOOF_SENDER,
            to_addrs=[data.CASE_MAILBOX],
            subject="Re: your request about line 4417",
            latest_text=data.SPOOF_REPLY,
            full_text=data.SPOOF_REPLY,
            received_at=base + timedelta(minutes=5),
        )
    )
    messages, _cursor = await env.mailbox.poll(data.CASE_MAILBOX, None)
    with factory() as session:
        case = _case(session, case_id)
        await process_inbound(
            session, messages, ai=env.ai, bus=SqlEventBus(), bound_case_id=case.id
        )
        accounts = _accounts(session, case.id)
        lines: list[str] = []
        caught = 0
        for ref in ("4417", "SB-88213", "CP-77120"):
            account = accounts[ref]
            check = session.scalar(
                select(OutcomeCheck)
                .where(OutcomeCheck.account_id == account.id)
                .order_by(OutcomeCheck.created_at.desc())
            )
            if check is None:
                lines.append(f"{ref}: no check was recorded")
                continue
            bad = [k for k, v in check.results.items() if v == "violated"]
            extras = list(check.results.get("unauthorised") or [])
            if ref == "4417":
                env.live["reply_card"] = _reply_card(check, northline_reading)
            if check.verdict == "needs_decision":
                caught += 1
                has_card = session.scalar(
                    select(Decision.id).where(
                        Decision.case_id == case.id, Decision.kind == "outcome_review"
                    )
                )
                if has_card is None:
                    session.add(
                        Decision(
                            case_id=case.id,
                            kind="outcome_review",
                            payload={
                                "account_id": str(account.id),
                                "violated": bad,
                                "unauthorised": extras,
                            },
                            options=[
                                {"id": "ask", "label": "Ask them to fix it"},
                                {"id": "call", "label": "Call them for me"},
                                {"id": "accept", "label": "Accept anyway"},
                            ],
                            status=DecisionStatus.open,
                        )
                    )
                lines.append(
                    f"{ref} Northline: NOT accepted as done. Violated: {', '.join(bad) or 'none'}; "
                    f"not in the plan: {', '.join(extras) or 'none'}. Number kept was not stated."
                )
            else:
                lines.append(
                    f"{ref}: verdict {check.verdict} (service {account.status_service.value}, "
                    f"money {account.status_money.value})."
                )
        held = session.scalars(
            select(Message).where(
                Message.case_id == case.id,
                Message.direction == MessageDirection.inbound,
                Message.recipient_check == RecipientCheck.unapproved,
            )
        ).all()
        money_lines = [
            f"Money: {m.kind.value} ${m.amount} is {m.status.value.replace('_', ' ')}."
            for m in session.scalars(select(MoneyItem).where(MoneyItem.case_id == case.id))
        ]
        held_count = len(held)
        session.commit()
    return StepResult(
        step_id="reply",
        title="Providers reply; 'done' is checked, not believed",
        headline=f"{caught} wrong outcome caught (Northline said done, broke the voicemail condition and added an unapproved 24-month contract); {held_count} lookalike message held",
        details=lines
        + [
            f"{held_count} message from {data.SPOOF_SENDER} asked for the will and bank details. "
            "It is not an approved address, so it was stored, held and nothing was disclosed.",
            *money_lines,
            "StreamBox and City Power replies matched the plan and carried their completion evidence, so those accounts are Done.",
        ],
        real=[
            "process_inbound: recipient check, quoted history stripped, quote verification, commitments stored",
            "outcome_check compares each reply with the approved plan version",
            "assess_money: a promised refund is 'issued, not yet on a statement', never 'received'",
        ],
        simulated=[
            "The three provider replies are typed text; the 'reading' of each is registered on FakeAI "
            "(a live model reads them in production; code verifies every quote either way)",
            "Delivery is the in-memory FakeMailbox",
        ],
        chat=[
            "Decision card (simulated Telegram): Northline says the transfer is complete, but the voicemail "
            "will be reset and a 24-month plan was added. [Ask them to fix it] [Call them for me] [Accept anyway]"
        ],
        links=["desk", "provider"],
    )


# --------------------------------------------------------------------------------------
# 9. Call
# --------------------------------------------------------------------------------------
async def step_call(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """The family picks 'Call them for me'. The agent has no way to accept terms."""
    del env
    sample = [
        ("Could you keep the voicemail on the 12-month option?", "asks"),
        ("Yes, we accept the 24-month plan.", "tries to accept"),
        ("Go ahead, it's a deal.", "tries to close the deal"),
        ("Sure, sounds good to me.", "a paraphrase"),
    ]
    with factory() as session:
        case = _case(session, case_id)
        decision = session.scalar(
            select(Decision).where(Decision.case_id == case.id, Decision.kind == "outcome_review")
        )
        if decision is None:
            raise ShowcaseError("There is no Northline decision yet. Run the reply step first.")
        if decision.status is DecisionStatus.open:
            decision.status = DecisionStatus.chosen
            decision.chosen = "call"
            _event(
                session, case.id, "decision.chosen", SARA, choice="call", decision="outcome_review"
            )
        northline = _accounts(session, case.id)["4417"]
        approved_plan = latest_plan(session, northline.id)
        session.commit()
        plan_v = approved_plan.version if approved_plan else 0
    screened = [(text, how, commitment_tripped(text)) for text, how in sample]
    return StepResult(
        step_id="call",
        title="'Call them for me': the agent cannot accept",
        headline="Sara chose 'Call them for me'; the guard blocks any acceptance wording from the agent",
        details=[
            *[
                f"Agent line “{t}” ({how}): {'BLOCKED by the guard' if tripped else 'allowed'}"
                for t, how, tripped in screened
            ],
            "A paraphrase can slip past a wording guard. That is why the real protection is structural: "
            "the agent has no tool that accepts, and acceptance is a server-built sentence.",
            f"Anything the representative offers that is not in approved plan v{plan_v} (a 12-month contract, a price) "
            "is only reported to Sara. Acceptance, if she agrees, is a server-built sentence bound to the terms she saw; "
            "if the terms change mid-call the approval is void.",
            "Open the call room to play Northline yourself. It is a browser call, not a phone call.",
        ],
        real=[
            "The family's choice is recorded on the decision row",
            "commitment_tripped screens the agent's own words (a heuristic, not a perfect guard)",
        ],
        simulated=[
            "The representative on the call is you or a judge, typing or speaking in the call room",
            "No phone call is made",
        ],
        links=["call", "desk"],
    )


# --------------------------------------------------------------------------------------
# 10. +14 days
# --------------------------------------------------------------------------------------
async def step_clock(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """Move the demo clock past every response window and let the runner decide what to do."""
    with factory() as session:
        case = _case(session, case_id)
        now = datetime.now(UTC)
        waits = [
            (job.run_at_case_time - case_now(case, now)).total_seconds()
            for job in session.scalars(
                select(Job).where(
                    Job.case_id == case.id, Job.kind == "followup", Job.status == JobStatus.pending
                )
            )
        ]
        if not waits:
            raise ShowcaseError("No follow-ups are scheduled. Run the send step first.")
        days = max(1, math.ceil((max(waits) + 3600) / 86400))
        advance_case_clock(session, case.id, days * 86400)
        session.commit()
    fired = await run_jobs(factory, env)
    with factory() as session:
        case = _case(session, case_id)
        accounts = {
            a.id: a for a in session.scalars(select(Account).where(Account.case_id == case.id))
        }
        lines: list[str] = []
        sent_followups = 0
        for job in session.scalars(
            select(Job).where(Job.case_id == case.id, Job.kind == "followup")
        ):
            who = accounts.get(UUID(str(job.payload["reason"]["account_id"])))
            name = f"{who.account_ref}" if who else "?"
            if job.status is JobStatus.succeeded:
                sent_followups += 1
                lines.append(f"{name}: no reply in the window, so the follow-up ran.")
            elif job.status is JobStatus.cancelled:
                lines.append(
                    f"{name}: follow-up cancelled ({job.last_error}): it already has an answer."
                )
            else:
                lines.append(f"{name}: follow-up {job.status.value}.")
        follow = session.scalars(
            select(Action).where(Action.case_id == case.id, Action.idem_key.like("followup:%"))
        ).all()
        sent = [a for a in follow if a.status in {ActionStatus.sent, ActionStatus.reconciled}]
        fit = accounts and next((a for a in accounts.values() if a.account_ref == "FL-5531"), None)
        if fit is not None and sent:
            fit.next_step = {
                "owner": "provider",
                "action": "Follow-up sent; waiting",
                "provider": "FitLife Gym",
            }
        session.commit()
    return StepResult(
        step_id="clock",
        title="+14 days: the follow-up runs by itself",
        headline=f"Clock moved +{days} days; {len(sent)} follow-up sent (FitLife), the others cancelled because they were answered",
        details=lines
        + [
            f"{fired} jobs ran. The follow-up went in the same thread, under the same approved plan and hash."
        ],
        real=[
            "advance_case_clock moves case time (demo cases only); the lease query reads it",
            "Each follow-up job re-checked: policy, mailbox, plan current, approval current, 'reason still true'",
            "The follow-up queued a send_request job, which re-checked the recipient before sending",
        ],
        simulated=[
            "Fourteen days did not pass; the case clock was moved. Gmail is the in-memory FakeMailbox"
        ],
        links=["desk"],
    )


# --------------------------------------------------------------------------------------
# 11. Hand-back
# --------------------------------------------------------------------------------------
async def step_handback(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """What a person must do: bank, no-email providers, insurer. Prepared here, done by them."""
    del env
    lines: list[str] = []
    with factory() as session:
        case = _case(session, case_id)
        accounts = _accounts(session, case.id)
        bank = _need(accounts, "0932")
        status, step = match_document_requirement("certified_copy", "photo")
        bank.status_docs = status
        bank.next_step = {**step, "provider": "Crescent Bank"}
        lines.append(
            f"Crescent Bank 0932: needs a certified copy; Sara holds a photo. {step['action']}"
        )
        for ref, channel in (("HW-20418", "web form"), ("PB-3017", "web form")):
            account = _need(accounts, ref)
            action = reserve_action(
                session,
                case_id=case.id,
                kind="handoff",
                idem_key=f"showcase:handoff:{account.id}",
                request={
                    "account_id": str(account.id),
                    "channel": channel,
                    "provider": (account.next_step or {}).get("provider", ""),
                },
            )
            await execute_action(session, action, mailbox=None, bus=SqlEventBus())
            provider = (account.next_step or {}).get("provider", account.service_label)
            account.next_step = {
                "owner": "family",
                "provider": provider,
                "action": f"Close it on {provider}'s website; we prepared the wording",
            }
            lines.append(
                f"{provider} {ref}: no email route ({channel}). A hand-off packet was prepared; Sara submits it."
            )
        sync_locators(session, case.id, {"policy"}, by="Afterward")
        ml = _need(accounts, "ML-6610")
        ml.next_step = {
            **(ml.next_step or {}),
            "action": "Say whose this is; a policy locator is prepared for you to run",
        }
        lines.append(
            "Meridian Life ML-6610 is still unconfirmed. A policy locator is prepared; Sara runs it and the insurer answers her."
        )
        _event(session, case.id, "handback.prepared", "Afterward", accounts=3)
        session.commit()
    return StepResult(
        step_id="handback",
        title="What a person has to do",
        headline="Legal, government and no-email steps are prepared and handed to the family, not performed",
        details=lines
        + [
            HANDBACK_STEPS["copies"],
            HANDBACK_STEPS["probate"],
            HANDBACK_STEPS["government"],
        ],
        real=[
            "match_document_requirement: a photo never satisfies a certified-copy requirement",
            "Hand-off actions are rows; no email goes to a provider that does not accept it",
            "Locators are prepared; only the family can start them",
        ],
        simulated=[
            "Nothing is filed anywhere. Afterward never files probate, tax or government forms"
        ],
        links=["onboarding", "desk"],
    )


# --------------------------------------------------------------------------------------
# 12. Finish
# --------------------------------------------------------------------------------------
async def step_finish(factory: SessionFactory, env: ShowcaseEnv, case_id: UUID) -> StepResult:
    """'Did you finish everything?' answered from stored rows, never from a model."""
    del env
    with factory() as session:
        case = _case(session, case_id)
        everything = list(
            session.scalars(
                select(Account).where(Account.case_id == case.id).order_by(Account.created_at)
            )
        )
        left_out = [a for a in everything if a.ownership is Ownership.not_theirs]
        accounts = [a for a in everything if a.ownership is not Ownership.not_theirs]
        summary = finish_summary([(a, True) for a in accounts])
        names = {p.id: p.name for p in session.scalars(select(ProviderProfile))}
        from app.engine.status import classify_account

        rows = [
            f"{names.get(a.provider_id) or (a.next_step or {}).get('provider') or a.service_label} "
            f"{a.account_ref}: {classify_account(a, conditions_hold=True).replace('_', ' ')}"
            for a in accounts
        ]
        sent = session.scalars(
            select(Action).where(
                Action.case_id == case.id,
                Action.kind == "email_send",
                Action.status.in_([ActionStatus.sent, ActionStatus.reconciled]),
            )
        ).all()
        wrong = session.scalars(
            select(OutcomeCheck).where(
                OutcomeCheck.case_id == case.id, OutcomeCheck.verdict == "needs_decision"
            )
        ).all()
        approvals = session.scalars(
            select(Approval).where(
                Approval.case_id == case.id, Approval.status == ApprovalStatus.approved
            )
        ).all()
        decisions = session.scalars(
            select(Event).where(
                Event.case_id == case.id,
                Event.kind.in_(
                    ["ownership.set", "decision.chosen", "dependency.answered", "approval.granted"]
                ),
            )
        ).all()
        held = session.scalars(
            select(Message).where(
                Message.case_id == case.id, Message.recipient_check == RecipientCheck.unapproved
            )
        ).all()
        refunds = session.scalars(select(MoneyItem).where(MoneyItem.case_id == case.id)).all()
        not_done = len(accounts) - summary.confirmed
        organisations = len({str((a.request or {}).get("account_id")) for a in sent})
        pending = session.scalars(
            select(Job).where(
                Job.case_id == case.id, Job.status == JobStatus.pending, Job.kind == "followup"
            )
        ).all()
    return StepResult(
        step_id="finish",
        title="'Did you finish everything?'",
        headline=(
            f"Not everything. Only {summary.confirmed} of {len(accounts)} accounts "
            f"{'is' if summary.confirmed == 1 else 'are'} done with written evidence"
        ),
        details=[
            summary.text,
            *rows,
            f"{len(left_out)} candidate left out because the family said it is not his.",
            f"Stated once. {organisations} requests sent (plus follow-ups), {len(approvals)} approvals, {len(decisions)} family decisions or answers, "
            f"{len(wrong)} wrong outcome(s) caught, {len(held)} lookalike message(s) held, {len(refunds)} refund(s) tracked as promised/issued, not received.",
            f"{len(pending)} follow-up(s) remain scheduled. {not_done} accounts are open, promised, handed back or unconfirmed.",
            "The list itself is not complete: " + "; ".join(NOT_SEARCHED) + ".",
        ],
        real=[
            "finish_summary buckets come from stored dimensions: service, money, documents, next step",
            "Every number above is a count over Postgres rows",
        ],
        simulated=[
            "The providers, Gmail and Telegram were simulated; the case rows are what a live run writes"
        ],
        links=["desk", "onboarding"],
    )


STEPS: tuple[Step, ...] = (
    Step("intent", "Sara states it once", "Voice note to verified facts", step_intent),
    Step("discover", "Find candidate accounts", "Inbox headers, Sara ticks, photos", step_discover),
    Step("confirm", "Family confirms", "Only the family decides ownership", step_confirm),
    Step("dependency", "Amina's answer", "A dependency rewrites the plan", step_dependency),
    Step("approve", "Specific approval", "Exact hashes, four requests", step_approve),
    Step("steady", "Autopilot: Steady", "Follow-ups stop asking first", step_steady),
    Step("send", "Send via the job runner", "Preflight, then Gmail (simulated)", step_send),
    Step("reply", "Replies are checked", "The wrong outcome is caught", step_reply),
    Step("call", "Call them for me", "The agent cannot accept", step_call),
    Step("clock", "+14 days", "A follow-up runs by itself", step_clock),
    Step("handback", "Hand-back", "What a person must do", step_handback),
    Step("finish", "Did you finish?", "The honest answer", step_finish),
)
STEP_IDS = tuple(step.id for step in STEPS)


async def run_step(factory: SessionFactory, env: ShowcaseEnv, step_id: str) -> StepResult:
    """Run one step against the current showcase case. Re-running a step is safe."""
    step = next((s for s in STEPS if s.id == step_id), None)
    if step is None:
        raise ShowcaseError("Unknown step")
    with factory() as session:
        case = showcase_case(session)
        if case is None:
            raise ShowcaseError("The showcase is not started. Press Reset to seed the start state.")
        case_id = case.id
        done = {s["step_id"] for s in progress(session)}
    earlier = STEP_IDS[: STEP_IDS.index(step_id)]
    missing = [e for e in earlier if e not in done]
    if missing:
        raise ShowcaseError(f"Run '{missing[0]}' first.")
    result = await step.run(factory, env, case_id)
    with factory() as session:
        _record(session, case_id, result)
        session.commit()
    return result


async def run_next(factory: SessionFactory, env: ShowcaseEnv) -> StepResult | None:
    """Run the first step not yet done. None means the showcase is finished."""
    with factory() as session:
        done = {s["step_id"] for s in progress(session)}
    for step in STEPS:
        if step.id not in done:
            return await run_step(factory, env, step.id)
    return None


# --------------------------------------------------------------------------------------
# Guided tour: state and the "you play the role" moments
# --------------------------------------------------------------------------------------
TOUR_ID = "showcase_tour"
LIVE_LABEL = "Live model"
RECORDED_LABEL = "Recorded model output"


class LiveInputError(ShowcaseError):
    """What the presenter typed cannot be used. The message says what to try."""


def tour_state(session: Session) -> dict[str, Any]:
    """Tour position and the cards of the live moments already played (survives page loads)."""
    row = session.get(DeskSnapshot, TOUR_ID)
    payload = dict(row.payload) if row is not None else {}
    return {
        "active": bool(payload.get("active")),
        "index": int(payload.get("index") or 0),
        "live": dict(payload.get("live") or {}),
    }


def save_tour_state(session: Session, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a position update; `live` entries are merged per moment."""
    state = tour_state(session)
    if "active" in patch:
        state["active"] = bool(patch["active"])
    if "index" in patch:
        state["index"] = max(0, min(int(patch["index"]), len(data.TOUR) - 1))
    if isinstance(patch.get("live"), dict):
        state["live"].update(patch["live"])
    row = session.get(DeskSnapshot, TOUR_ID)
    if row is None:
        session.add(DeskSnapshot(id=TOUR_ID, payload=state))
    else:
        row.payload = state
    session.flush()
    return state


def clear_tour_live(session: Session) -> None:
    """A reset forgets the typed-in moments but keeps where the tour is."""
    if session.get(DeskSnapshot, TOUR_ID) is not None:
        save_tour_state(session, {})
        row = session.get(DeskSnapshot, TOUR_ID)
        row.payload = {**row.payload, "live": {}}
        session.flush()


def _later_steps_done(factory: SessionFactory, step_id: str) -> bool:
    later = set(STEP_IDS[STEP_IDS.index(step_id) + 1 :])
    with factory() as session:
        return any(item["step_id"] in later for item in progress(session))


def _guard_replay(factory: SessionFactory, step_id: str) -> None:
    if _later_steps_done(factory, step_id):
        raise LiveInputError(
            "That moment is already behind us. Reset the showcase to play it again."
        )


async def live_intake(
    factory: SessionFactory, env: ShowcaseEnv, text: str, ai: Any | None
) -> dict[str, Any]:
    """Sara's words through the real intake reading, then the same quote check as the scripted step."""
    text = text.strip()
    if not text:
        raise LiveInputError("Say or type what Sara would say first.")
    _guard_replay(factory, "intent")
    label, reading, note = RECORDED_LABEL, None, ""
    if ai is not None:
        try:
            reading = await ai.structured("intake", IntakeOut, intake_messages(text))
            label = LIVE_LABEL
        except CrisisPaused:
            raise LiveInputError(
                "That sounds like Sara may need support. The assistant pauses here and a person takes over."
            ) from None
        except Exception:
            logger.info("showcase live", extra={"kind": "showcase.live.intake", "ok": False})
            note = "The live model did not answer, so the recorded reading is shown."
    if reading is not None:
        env.live["intake"] = {"text": text, "reading": reading, "source": "live"}
    else:
        env.live.pop("intake", None)
        note = (
            note
            or "No model key is configured, so the recorded reading of the scripted voice note is shown."
        )
    result = await run_step(factory, env, "intent")
    return {
        "source": label,
        "note": note,
        "text": text if reading is not None else data.SARA_TRANSCRIPT,
        "card": env.live.get("intake_card"),
        "headline": result.headline,
    }


async def live_dependency(
    factory: SessionFactory, env: ShowcaseEnv, text: str, ai: Any | None
) -> dict[str, Any]:
    """Amina's answer through the real dependency reading; code turns it into plan conditions."""
    text = text.strip()
    if not text:
        raise LiveInputError("Say or type what Amina would answer first.")
    _guard_replay(factory, "dependency")
    label, answer, note = RECORDED_LABEL, None, ""
    if ai is not None:
        try:
            raw = await ai.structured("dependency", DependencyOut, dependency_messages(text))
            answer = verify_dependency(raw, text)
            label = LIVE_LABEL
        except Exception:
            logger.info("showcase live", extra={"kind": "showcase.live.dependency", "ok": False})
            note = "The live model did not answer, so the recorded reading is shown."
        else:
            if answer is None or answer.kind not in {"access", "memory", "shared_service"}:
                raise LiveInputError(
                    "No supported answer found in those words. Say who uses the line, "
                    "for example: that is my number, and his voice is on the voicemail."
                )
    if answer is not None:
        env.live["dependency"] = {"text": text, "answer": answer, "source": "live"}
    else:
        env.live.pop("dependency", None)
        note = (
            note
            or "No model key is configured, so the recorded reading of Amina's answer is shown."
        )
    result = await run_to(factory, env, "dependency")
    card = dict(env.live.get("dependency_card") or {})
    return {"source": label, "note": note, "card": card, "headline": result.headline}


async def live_reply(
    factory: SessionFactory, env: ShowcaseEnv, text: str, ai: Any | None
) -> dict[str, Any]:
    """The presenter plays Northline. The real reply reader and outcome check judge the words."""
    text = text.strip()
    if not text:
        raise LiveInputError("Type the reply Northline would send first.")
    with factory() as session:
        if "reply" in {item["step_id"] for item in progress(session)}:
            raise LiveInputError(
                "Northline has already replied. Reset the showcase to play it again."
            )
    label, reading, note = RECORDED_LABEL, None, ""
    if ai is not None:
        try:
            reading = await extract_verified_reply(
                ai, strip_quoted_history(text), ["4417"], thread_ref="4417"
            )
            label = LIVE_LABEL
        except Exception:
            logger.info("showcase live", extra={"kind": "showcase.live.reply", "ok": False})
            note = "The live model did not answer, so the recorded reading is shown."
    if reading is not None:
        env.live["reply"] = {"text": text, "reading": reading, "source": "live"}
    else:
        env.live.pop("reply", None)
        note = (
            note
            or "No model key is configured, so the recorded Northline reply and its reading are shown."
        )
    result = await run_to(factory, env, "reply")
    return {
        "source": label,
        "note": note,
        "text": text if reading is not None else data.NORTHLINE_REPLY.split("\n\nOn ")[0],
        "card": env.live.get("reply_card"),
        "headline": result.headline,
    }


async def run_to(factory: SessionFactory, env: ShowcaseEnv, step_id: str) -> StepResult:
    """Run every step up to and including `step_id` that is not done yet; return that step's result."""
    if step_id not in STEP_IDS:
        raise ShowcaseError("Unknown step")
    result: StepResult | None = None
    for step in STEPS:
        with factory() as session:
            done = {item["step_id"] for item in progress(session)}
        if step.id not in done:
            result = await run_step(factory, env, step.id)
        if step.id == step_id:
            break
    if result is None or result.step_id != step_id:
        with factory() as session:
            row = next((i for i in progress(session) if i["step_id"] == step_id), None)
        if row is None:
            raise ShowcaseError("That step has not run.")
        return StepResult(**row)
    return result


__all__ = [
    "STEPS",
    "STEP_IDS",
    "ContractError",
    "LIVE_LABEL",
    "RECORDED_LABEL",
    "LiveInputError",
    "ShowcaseEnv",
    "ShowcaseError",
    "StepResult",
    "is_showcase_case",
    "live_dependency",
    "live_intake",
    "live_reply",
    "run_to",
    "save_tour_state",
    "tour_state",
    "progress",
    "reset_showcase",
    "run_next",
    "run_step",
    "seed_showcase_start",
    "showcase_case",
]
