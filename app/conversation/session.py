"""Family conversation. Buttons confirm choices; model output cannot add a recipient."""

import contextlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from app.ai.schemas import DependencyOut, IntakeOut
from app.channels.audio import Runner, transcribe_ogg
from app.contracts import AIClient, Option
from app.conversation.cards import (
    ApprovalCard,
    build_approval_card,
    read_back_decision,
)
from app.conversation.commands import Controls, apply_command, status_text
from app.conversation.crisis import CARE_TEXT, CONTINUE, PAUSED_TEXT
from app.conversation.dependency import (
    PlanItem,
    ProviderFacts,
    RevisedPlan,
    dependency_messages,
    render_revision,
    revise_plan,
)
from app.conversation.digest import weekly_digest
from app.conversation.finish import finish_reply
from app.conversation.intake import (
    CONFIRM,
    FIX,
    confirmation_text,
    intake_messages,
    supported_value,
)
from app.conversation.routing import (
    is_crisis,
    is_decision,
    is_finish_question,
    is_off_topic,
    is_question,
    parse_command,
    parse_start,
)
from app.discovery.agent import (
    AgentRunner,
    DiscoveryTools,
    Suggestion,
    apply_answer,
    baseline_suggestions,
    close_stale,
    run_discovery,
)
from app.discovery.candidates import Candidate, confirm_candidate, ingest_email, ingest_photo
from app.discovery.coverage import Coverage, coverage_panel, render_coverage
from app.discovery.directory import lookup
from app.discovery.household import DECEASED, HouseholdScan, NotOwner
from app.discovery.vault import VaultCipher, VaultItem, intake_document

VOICE_PROMPT = "Bereavement administration. The speaker may mention Yusuf Malik, Sara or Amina."
VOICE_KEYWORDS = ("Yusuf Malik", "Sara", "Amina", "Northline", "Crescent")
DECLINE = (
    "I can only help with the admin after a death: accounts, documents, "
    "and what the family asked us to do."
)
STOPPED = "The case is stopped, including monitoring. Say resume when you want to continue."
_DECISION_IDS = frozenset({"keep_line", "close_line", "hold_safe", "not_now", "see_plan"})
_FIND = re.compile(r"^\s*(/find|find (his |the )?accounts?)\s*[.!]?\s*$", re.I)
_READ = re.compile(r"^\s*read\s+(all|[\d\s,]+(?:and\s*[\d\s,]*)?)\s*[.!]?\s*$", re.I)
_SHARED_CATEGORIES = frozenset({"mobile", "broadband", "landline"})
DISCOVERY_ASK = "Where should I look for his accounts? Nothing is searched until you choose."
SEARCH_INBOX = Option(id="disc:inbox", label="Search an inbox")
PHOTOS_FORWARDS = Option(id="disc:photos", label="Photos/forwards")
LATER = Option(id="disc:later", label="Later")
NOT_NOW_READ = Option(id="disc:notnow", label="Not now")


@dataclass(frozen=True)
class Invite:
    """A household deep link. The role it grants is stated, not verified."""

    token: str
    name: str
    stated_role: str


@dataclass
class MemberRecord:
    """Someone on the conversation. `role` is owner or household."""

    sender: str
    name: str
    role: str
    stated_role: str


@dataclass
class Outbound:
    """One message the gateway can send. Options are already within the button limit."""

    to: str
    text: str
    options: list[Option] | None = None
    kind: str = "text"


@dataclass
class ConversationState:
    """Working state for one case conversation. Durable rows belong to the engine."""

    intake: IntakeOut | None = None
    intake_source: str = ""
    intake_confirmed: bool = False
    awaiting_fix: bool = False
    paused: bool = False
    controls: Controls = field(default_factory=Controls)
    members: dict[str, MemberRecord] = field(default_factory=dict)
    owner_sender: str | None = None
    deceased_name: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    coverage: Coverage | None = None
    emails_ingested: int = 0
    photos_ingested: int = 0
    open_dependency: dict[str, str] = field(default_factory=dict)
    plan: RevisedPlan | None = None
    approval: ApprovalCard | None = None
    approval_choice: str | None = None
    decision_choice: str | None = None
    quiet_days: set[date] = field(default_factory=set)
    vault_items: list[VaultItem] = field(default_factory=list)
    suggestions_shown: set[str] = field(default_factory=set)
    awaiting_ticks: bool = False
    discovery_runs: int = 0


class Conversation:
    """Routes a turn and keeps the Malik-style intake, discovery and approval flow."""

    def __init__(
        self,
        ai: AIClient,
        *,
        providers: Mapping[str, ProviderFacts],
        allowed_recipients: Sequence[str],
        line: ProviderFacts,
        invites: Mapping[str, Invite] | None = None,
        case_date: date | None = None,
        runner: Runner | None = None,
        finish_summary: Mapping[str, object] | None = None,
        snapshot: Mapping[str, object] | None = None,
        scan: HouseholdScan | None = None,
        discovery_runner: AgentRunner | None = None,
        discovery: bool = False,
        connect_url: str | None = None,
    ) -> None:
        self.ai = ai
        self.providers = dict(providers)
        self.allowed_recipients = tuple(allowed_recipients)
        self.line = line
        self.invites = dict(invites or {})
        self.runner = runner
        self.finish_summary = dict(finish_summary) if finish_summary is not None else None
        self.snapshot = dict(snapshot or {})
        self.state = ConversationState()
        self.state_case_date = case_date
        self.scan = scan
        self.discovery_runner = discovery_runner
        self.discovery = discovery or scan is not None or discovery_runner is not None
        self.connect_url = connect_url
        self.tools = DiscoveryTools(candidates=self.state.candidates, scan=scan)
        self.case_id: UUID | None = None
        self.scan_connection_id: UUID | None = None
        self.last_dependency: dict[str, object] | None = None

    @property
    def case_date(self) -> date | None:
        return self.state_case_date

    async def handle_voice(
        self, sender: str, ogg: bytes, *, now: datetime | None = None
    ) -> list[Outbound]:
        transcript = await transcribe_ogg(
            self.ai,
            ogg,
            prompt=VOICE_PROMPT,
            keywords=VOICE_KEYWORDS,
            runner=self.runner,
        )
        return await self.handle_text(sender, transcript.text, now=now)

    async def handle_text(
        self, sender: str, text: str, *, now: datetime | None = None
    ) -> list[Outbound]:
        moment = now or datetime.now(UTC)
        if is_crisis(text):
            self.state.paused = True
            return [Outbound(sender, CARE_TEXT, options=[CONTINUE], kind="crisis")]
        started = parse_start(text)
        if started is not None:
            return self._join(sender, started)
        command = parse_command(text)
        if command is not None:
            return self._command(sender, command, moment)
        if self.state.controls.control == "stopped":
            return [Outbound(sender, STOPPED, kind="stopped")]
        if self.state.paused:
            if text.strip().lower() == "continue":
                self.state.paused = False
                return [Outbound(sender, "We can pick the admin back up whenever you're ready.")]
            return [Outbound(sender, PAUSED_TEXT, options=[CONTINUE], kind="paused")]
        if self.discovery and self.state.intake_confirmed:
            if _FIND.match(text):
                return [self.discovery_card(sender)]
            picked = _READ.match(text)
            if picked is not None and self.state.awaiting_ticks:
                return await self._read_chosen(sender, picked.group(1))
        if self.state.awaiting_fix:
            return await self._intake(sender, text)
        if is_off_topic(text):
            return [Outbound(sender, DECLINE, kind="off_topic")]
        if is_finish_question(text):
            return [Outbound(sender, finish_reply(self.finish_summary), kind="finish")]
        if sender in self.state.open_dependency:
            return await self._dependency_answer(sender, text)
        if self.state.intake_confirmed and is_decision(text):
            return self._offer_decision(sender, text)
        if is_question(text):
            return [Outbound(sender, self._answer_question(text), kind="question")]
        if not self.state.intake_confirmed:
            return await self._intake(sender, text)
        return [Outbound(sender, DECLINE, kind="off_topic")]

    async def handle_button(
        self, sender: str, button_id: str, *, now: datetime | None = None
    ) -> list[Outbound]:
        del now
        if button_id == "continue_admin":
            self.state.paused = False
            return [Outbound(sender, "We can pick the admin back up whenever you're ready.")]
        if self.state.paused:
            return [Outbound(sender, PAUSED_TEXT, options=[CONTINUE], kind="paused")]
        if self.state.controls.control == "stopped":
            return [Outbound(sender, STOPPED, kind="stopped")]
        if button_id == "confirm_intake":
            if self.state.intake is None:
                return [Outbound(sender, "I don't have a summary to confirm yet.")]
            self.state.intake_confirmed = True
            self.state.awaiting_fix = False
            replies = [
                Outbound(sender, "Thank you. I've saved that summary.", kind="intake_confirmed")
            ]
            if self.discovery:
                replies.append(self.discovery_card(sender))
            return replies
        if button_id == "fix_intake":
            self.state.awaiting_fix = True
            self.state.intake_confirmed = False
            return [
                Outbound(
                    sender,
                    "What should I change? I won't contact any organisation until you confirm "
                    "the corrected summary.",
                    kind="intake_fix",
                )
            ]
        if button_id == "approve_plan":
            return self._approve(sender)
        if button_id == "change_plan":
            return [
                Outbound(
                    sender,
                    "What would you like to change? I haven't sent the request.",
                    kind="approval_change",
                )
            ]
        if button_id == "review_candidates":
            lines = [f"• {item.service_label} ({item.ownership})" for item in self.state.candidates]
            listing = "\n".join(lines) if lines else "No candidates yet."
            return [
                Outbound(
                    sender,
                    f"Possible accounts. This list stays open.\n{listing}",
                    kind="review",
                )
            ]
        if button_id in _DECISION_IDS:
            return self._choose_decision(sender, button_id)
        if self.discovery and button_id.startswith(("disc:", "sg:")):
            return await self._discovery_button(sender, button_id)
        return [Outbound(sender, "I don't have that button on the current card.")]

    def ask_dependency(self, sender: str) -> list[Outbound]:
        """Ask the household member about the line before anything changes."""
        self.line = self.shared_line()
        self.state.open_dependency[sender] = self.line.account_ref
        member = self.state.members.get(sender)
        name = member.name.split()[0] if member is not None else "there"
        text = (
            f"{name}, one question before anything changes with {self.line.name}, "
            f"the line ending {self.line.account_ref}: does anyone still use this number, "
            "or does it get codes for any other account?"
        )
        return [Outbound(sender, text, kind="dependency_question")]

    async def ingest_forward(self, body: str, evidence: str) -> None:
        result = await ingest_email(self.ai, body, self.state.candidates, evidence=evidence)
        self.state.candidates = result.candidates
        self.state.emails_ingested += 1

    async def ingest_picture(
        self,
        *,
        image: bytes,
        mime: str,
        label: str,
        evidence: str,
        cipher: VaultCipher,
    ) -> VaultItem:
        result = await ingest_photo(
            self.ai,
            image,
            mime,
            label,
            self.state.candidates,
            evidence=evidence,
        )
        self.state.candidates = result.candidates
        self.state.photos_ingested += 1
        item = intake_document(
            doc=result.document,
            raw_form=result.raw_form,
            image=image,
            cipher=cipher,
            source="phone_photo",
            case_date=self.state_case_date,
            deceased_name=self.state.deceased_name,
        )
        self.state.vault_items.append(item)
        return item

    def apply_labels(self, labels: Mapping[str, str]) -> None:
        for item in self.state.candidates:
            if item.account_ref in labels:
                item.service_label = labels[item.account_ref]

    def confirm_refs(self, refs: set[str]) -> None:
        """Record family confirmations. The model cannot call this."""
        for ref in refs:
            confirm_candidate(self.state.candidates, ref)

    def refresh_coverage(self) -> Coverage:
        coverage = coverage_panel(
            self.state.candidates,
            emails=self.state.emails_ingested,
            photos=self.state.photos_ingested,
        )
        self.state.coverage = coverage
        return coverage

    def coverage_outbound(self, sender: str) -> Outbound:
        coverage = self.refresh_coverage()
        text = render_coverage(
            coverage,
            emails=self.state.emails_ingested,
            photos=self.state.photos_ingested,
            total=len(self.state.candidates),
        )
        return Outbound(
            sender,
            text,
            options=[Option(id="review_candidates", label="Review")],
            kind="coverage",
        )

    def digest(self, lines: Sequence[str], *, on: date) -> str | None:
        stopped = self.state.controls.control == "stopped" or not self.state.controls.monitoring
        return weekly_digest(
            lines,
            on=on,
            quiet_days=self.state.quiet_days,
            quiet_until=self.state.controls.quiet_until,
            stopped=stopped,
        )

    def set_quiet_days(self, days: set[date]) -> None:
        self.state.quiet_days = set(days)

    # ---- discovery -------------------------------------------------------------------------

    def _sync_tools(self) -> DiscoveryTools:
        self.tools.candidates = self.state.candidates
        self.tools.scan = self.scan
        self.tools.ai = self.ai
        return self.tools

    def _may_use_inbox(self, sender: str) -> bool:
        owner = self.scan.owner if self.scan is not None else None
        return sender == self.state.owner_sender or (owner is not None and sender == owner)

    def discovery_card(self, sender: str) -> Outbound:
        """Ask where to look. Nothing is searched until a button is pressed."""
        return Outbound(
            sender,
            DISCOVERY_ASK,
            options=[SEARCH_INBOX, PHOTOS_FORWARDS, LATER],
            kind="discovery_offer",
        )

    async def _discovery_button(self, sender: str, button_id: str) -> list[Outbound]:
        if button_id.startswith("sg:"):
            return self._suggestion_answer(sender, button_id)
        if button_id == "disc:later":
            return [
                Outbound(
                    sender,
                    "Okay. Say find accounts whenever you want me to start looking.",
                    kind="discovery_later",
                )
            ]
        if button_id == "disc:photos":
            return [
                Outbound(
                    sender,
                    "Send a photo of a bill or letter, or forward a message. "
                    "I read only what you send me, and I'll say where each account came from.",
                    kind="discovery_photos",
                )
            ]
        if button_id == "disc:inbox":
            return await self._inbox_search(sender)
        if button_id == "disc:notnow":
            self.state.awaiting_ticks = False
            return [Outbound(sender, "Okay. Nothing has been read.", kind="discovery_later")]
        if button_id == "disc:readall":
            return await self._read_chosen(sender, "all")
        if button_id == "disc:readreq":
            return await self._read_requested(sender)
        return [Outbound(sender, "I don't have that button on the current card.")]

    def _no_inbox_text(self) -> str:
        text = (
            "No inbox is connected yet. A family member can connect a household inbox, or "
            "Yusuf's own mailbox if they already have access to it and say on what authority. "
            "It is read-only: I list message headers first and read only the ones you tick."
        )
        if self.connect_url:
            text += f"\nConnect it here: {self.connect_url}"
        return text

    async def _inbox_search(self, sender: str) -> list[Outbound]:
        if self.scan is None:
            return [Outbound(sender, self._no_inbox_text(), kind="discovery_no_inbox")]
        if not self._may_use_inbox(sender):
            return [self._not_owner(sender)]
        try:
            await self.scan.search()
        except Exception:
            return [
                Outbound(
                    sender,
                    "I couldn't search that inbox just now. Nothing was read.",
                    kind="discovery_error",
                )
            ]
        listed = self.scan.listing()
        if not listed:
            return [
                Outbound(
                    sender,
                    "No messages matched the search. That doesn't mean there is nothing; "
                    "photos, statements and post can show more.",
                    kind="discovery_empty",
                )
            ]
        lines = [
            f"{number}. {_clip(h.sender, 40)} - {_clip(h.subject, 60)}"
            + (f" ({h.date})" if h.date else "")
            for number, h in enumerate(listed, start=1)
        ]
        self.state.awaiting_ticks = True
        text = (
            f"I found {len(listed)} messages that may be about accounts. "
            "These are headers only; I have not read any.\n"
            + "\n".join(lines)
            + "\nReply read 1 3 4 to choose, or tap the button."
        )
        return [
            Outbound(
                sender,
                text,
                options=[Option(id="disc:readall", label=f"Read all {len(listed)}"), NOT_NOW_READ],
                kind="discovery_headers",
            )
        ]

    def _not_owner(self, sender: str) -> Outbound:
        return Outbound(
            sender,
            "Only the person who connected this inbox, or the case owner, can choose what is "
            "read. I haven't read anything.",
            kind="discovery_not_owner",
        )

    async def _read_chosen(self, sender: str, chosen: str) -> list[Outbound]:
        scan = self.scan
        if scan is None:
            return [Outbound(sender, self._no_inbox_text(), kind="discovery_no_inbox")]
        by = scan.owner if self._may_use_inbox(sender) else sender
        try:
            if chosen.strip().lower() == "all":
                scan.tick([h.id for h in scan.listing()], by=by)
            else:
                numbers = [int(item) for item in re.findall(r"\d+", chosen)]
                ticked = scan.tick_numbers(numbers, by=by)
                if not ticked:
                    return [
                        Outbound(
                            sender,
                            "Those numbers aren't on the list, so I haven't read anything.",
                            kind="discovery_bad_numbers",
                        )
                    ]
        except NotOwner:
            return [self._not_owner(sender)]
        return await self._read_ticked_and_discover(sender)

    async def _read_requested(self, sender: str) -> list[Outbound]:
        scan = self.scan
        if scan is None:
            return [Outbound(sender, self._no_inbox_text(), kind="discovery_no_inbox")]
        by = scan.owner if self._may_use_inbox(sender) else sender
        try:
            scan.tick(list(self.tools.read_requests), by=by)
        except NotOwner:
            return [self._not_owner(sender)]
        return await self._read_ticked_and_discover(sender)

    async def _read_ticked_and_discover(self, sender: str) -> list[Outbound]:
        scan = self.scan
        assert scan is not None
        tools = self._sync_tools()
        self.state.awaiting_ticks = False
        read = failed = 0
        origin = "deceased_inbox" if scan.account_of == DECEASED else "household_inbox"
        for header, body in await scan.read_ticked():
            evidence_id = f"inbox:{header.id}"
            label = f"Inbox message from {_clip(header.sender, 60)}"
            tools.grant_evidence(evidence_id, label)
            try:
                result = await ingest_email(
                    self.ai, body, self.state.candidates, evidence=evidence_id
                )
            except Exception:
                failed += 1
                continue
            self.state.candidates = result.candidates
            tools.candidates = self.state.candidates
            read += 1
            for item in self.state.candidates:
                if evidence_id in item.evidence_ids:
                    if item.origin == "forwarded":
                        item.origin = origin
                    if item.evidence == evidence_id:
                        item.evidence = label
        await run_discovery(tools, self.discovery_runner)
        self.state.discovery_runs += 1
        coverage = self._discovery_coverage()
        total = len(self.state.candidates)
        pending = len(coverage.unconfirmed)
        note = f" {failed} could not be read." if failed else ""
        text = (
            f"I read {read} messages you chose.{note} That gives {total} possible accounts "
            f"so far; {pending} need you to say whose they are. Nothing is confirmed yet.\n"
            f"{scan.coverage_line() or ''}\n"
            f"Not searched: {'; '.join(coverage.not_searched[:3])}."
        )
        replies = [Outbound(sender, text.replace("\n\n", "\n"), kind="discovery_summary")]
        replies += self._next_suggestion(sender)
        replies += self._read_request_card(sender)
        return replies

    def _discovery_coverage(self) -> Coverage:
        scan = self.scan
        sources = [line] if scan is not None and (line := scan.coverage_line()) else []
        coverage = coverage_panel(
            self.state.candidates,
            emails=self.state.emails_ingested,
            photos=self.state.photos_ingested,
            sources=sources,
            his_inbox_connected=scan is not None and scan.account_of == DECEASED,
        )
        self.state.coverage = coverage
        return coverage

    def _read_request_card(self, sender: str) -> list[Outbound]:
        scan = self.scan
        if scan is None:
            return []
        wanted = [
            item
            for item in self.tools.read_requests
            if item in scan.headers and item not in scan.ticked
        ]
        if not wanted:
            return []
        lines = [f"- {_clip(scan.headers[i].subject, 60)}" for i in wanted[:8]]
        return [
            Outbound(
                sender,
                "I'd like to read these too. I haven't opened them.\n" + "\n".join(lines),
                options=[
                    Option(id="disc:readreq", label=f"Read these {len(wanted)}"),
                    NOT_NOW_READ,
                ],
                kind="discovery_read_request",
            )
        ]

    def _next_suggestion(self, sender: str) -> list[Outbound]:
        """One suggestion card at a time: none while a shown one is still open."""
        close_stale(self._sync_tools())
        open_items = [s for s in self.tools.suggestions if s.status == "open"]
        if any(s.id in self.state.suggestions_shown for s in open_items):
            return []
        for item in open_items:
            self.state.suggestions_shown.add(item.id)
            return [
                Outbound(
                    sender,
                    f"{item.text}\n({item.why})" if item.why else item.text,
                    options=list(item.options),
                    kind="suggestion",
                )
            ]
        return []

    def _suggestion_answer(self, sender: str, button_id: str) -> list[Outbound]:
        if sender not in self.state.members:
            return [
                Outbound(
                    sender,
                    "Only people on this case can answer that. I haven't changed anything.",
                    kind="suggestion_refused",
                )
            ]
        tools = self._sync_tools()
        suggestion, reply = apply_answer(tools, button_id)
        baseline_suggestions(tools)
        kind = "suggestion_answered" if suggestion is not None else "suggestion_stale"
        return [Outbound(sender, reply, kind=kind), *self._next_suggestion(sender)]

    async def photo_discovery(
        self,
        sender: str,
        label: str,
        *,
        doc_type: str = "",
        image: bytes | None = None,
        mime: str = "",
    ) -> list[Outbound]:
        """After a photo is read: record it as a source, run discovery, offer the next card.

        A photographed statement also lists its recurring payees as unconfirmed candidates.
        """
        if not self.discovery:
            return []
        tools = self._sync_tools()
        number = self.state.photos_ingested
        evidence_id = f"photo:{number}"
        text = f"Photo: {_clip(label, 60)}"
        tools.grant_evidence(evidence_id, text)
        for item in self.state.candidates:
            if evidence_id in item.evidence_ids and item.evidence == evidence_id:
                item.evidence = text
        if "statement" in doc_type.lower() and image is not None:
            doc_id = f"photo{number}"
            tools.grant_document(
                doc_id, f"Statement photo: {_clip(label, 50)}", image=image, mime=mime
            )
            with contextlib.suppress(Exception):
                await tools.statement_payees(doc_id)
        await run_discovery(tools, self.discovery_runner)
        self.state.discovery_runs += 1
        return self._next_suggestion(sender)

    def shared_line(self) -> ProviderFacts:
        """The line to ask a household member about: a flagged shared line with known facts."""
        for item in self.state.candidates:
            entry = lookup(item.provider)
            shared = (entry is not None and entry.category in _SHARED_CATEGORIES) or any(
                "shared" in note.lower() for note in item.notes
            )
            if not shared:
                continue
            for facts in self.providers.values():
                if facts.account_ref == item.account_ref:
                    return facts
        return self.line

    # ---- persistence -----------------------------------------------------------------------

    def export_state(self) -> dict[str, object]:
        """JSON-safe copy of the working state, so a restart does not lose the case."""
        st = self.state
        return {
            "intake": st.intake.model_dump(mode="json") if st.intake is not None else None,
            "intake_source": st.intake_source,
            "intake_confirmed": st.intake_confirmed,
            "awaiting_fix": st.awaiting_fix,
            "paused": st.paused,
            "controls": {
                "control": st.controls.control,
                "quiet_until": st.controls.quiet_until.isoformat()
                if st.controls.quiet_until
                else None,
                "monitoring": st.controls.monitoring,
                "org_actions": st.controls.org_actions,
            },
            "owner_sender": st.owner_sender,
            "deceased_name": st.deceased_name,
            "members": {key: asdict(member) for key, member in st.members.items()},
            "candidates": [asdict(item) for item in st.candidates],
            "emails_ingested": st.emails_ingested,
            "photos_ingested": st.photos_ingested,
            "open_dependency": dict(st.open_dependency),
            "last_dependency": self.last_dependency,
            "plan": _plan_to_dict(st.plan),
            "approval": _approval_to_dict(st.approval),
            "approval_choice": st.approval_choice,
            "decision_choice": st.decision_choice,
            "suggestions": [_suggestion_to_dict(item) for item in self.tools.suggestions],
            "suggestions_shown": sorted(st.suggestions_shown),
            "locators_started": sorted(self.tools.locators_started),
            "evidence": dict(self.tools.evidence),
            "awaiting_ticks": st.awaiting_ticks,
            "discovery_runs": st.discovery_runs,
        }

    def load_state(self, data: Mapping[str, object]) -> None:
        """Restore what `export_state` wrote. Unknown or damaged parts are skipped."""
        st = self.state
        intake = data.get("intake")
        if isinstance(intake, dict):
            try:
                st.intake = IntakeOut.model_validate(intake)
            except ValueError:
                st.intake = None
        st.intake_source = str(data.get("intake_source") or "")
        st.intake_confirmed = bool(data.get("intake_confirmed")) and st.intake is not None
        st.awaiting_fix = bool(data.get("awaiting_fix"))
        st.paused = bool(data.get("paused"))
        controls = data.get("controls")
        if isinstance(controls, dict):
            quiet = controls.get("quiet_until")
            st.controls = Controls(
                control=str(controls.get("control") or "active"),
                quiet_until=datetime.fromisoformat(quiet) if isinstance(quiet, str) else None,
                monitoring=bool(controls.get("monitoring", True)),
                org_actions=bool(controls.get("org_actions", True)),
            )
        owner = data.get("owner_sender")
        st.owner_sender = str(owner) if owner else None
        deceased = data.get("deceased_name")
        st.deceased_name = str(deceased) if deceased else None
        members = data.get("members")
        if isinstance(members, dict):
            st.members = {
                str(key): MemberRecord(
                    sender=str(row.get("sender", key)),
                    name=str(row.get("name", "")),
                    role=str(row.get("role", "household")),
                    stated_role=str(row.get("stated_role", "")),
                )
                for key, row in members.items()
                if isinstance(row, dict)
            }
        rows = data.get("candidates")
        if isinstance(rows, list):
            st.candidates = [_candidate_from_dict(row) for row in rows if isinstance(row, dict)]
        st.emails_ingested = int(data.get("emails_ingested") or 0)  # type: ignore[call-overload]
        st.photos_ingested = int(data.get("photos_ingested") or 0)  # type: ignore[call-overload]
        dependency = data.get("open_dependency")
        st.open_dependency = (
            {str(k): str(v) for k, v in dependency.items()} if isinstance(dependency, dict) else {}
        )
        last = data.get("last_dependency")
        self.last_dependency = dict(last) if isinstance(last, dict) else None
        st.plan = _plan_from_dict(data.get("plan"))
        st.approval = _approval_from_dict(data.get("approval"))
        choice = data.get("approval_choice")
        st.approval_choice = str(choice) if choice else None
        decided = data.get("decision_choice")
        st.decision_choice = str(decided) if decided else None
        st.suggestions_shown = {str(item) for item in data.get("suggestions_shown") or []}  # type: ignore[attr-defined]
        st.awaiting_ticks = bool(data.get("awaiting_ticks"))
        st.discovery_runs = int(data.get("discovery_runs") or 0)  # type: ignore[call-overload]
        tools = self._sync_tools()
        tools.suggestions = [
            _suggestion_from_dict(row)
            for row in data.get("suggestions") or []  # type: ignore[attr-defined]
            if isinstance(row, dict)
        ]
        tools.locators_started = {str(i) for i in data.get("locators_started") or []}  # type: ignore[attr-defined]
        evidence = data.get("evidence")
        tools.evidence = (
            {str(k): str(v) for k, v in evidence.items()} if isinstance(evidence, dict) else {}
        )

    async def _intake(self, sender: str, text: str) -> list[Outbound]:
        result = await self.ai.structured("intake", IntakeOut, intake_messages(text))
        if not isinstance(result, IntakeOut):
            result = IntakeOut.model_validate(result.model_dump())
        self.state.intake = result
        self.state.intake_source = text
        self.state.intake_confirmed = False
        self.state.awaiting_fix = False
        role = supported_value(result.stated_role, text) or ""
        speaker = supported_value(result.speaker_name, text) or sender
        deceased = supported_value(result.deceased_name, text)
        if deceased:
            self.state.deceased_name = deceased
        if self.state.owner_sender is None:
            self.state.owner_sender = sender
            self.state.members[sender] = MemberRecord(sender, speaker, "owner", role)
        body = confirmation_text(result, text, self.state_case_date)
        return [Outbound(sender, body, options=[CONFIRM, FIX], kind="intake_card")]

    async def _dependency_answer(self, sender: str, text: str) -> list[Outbound]:
        result = await self.ai.structured("dependency", DependencyOut, dependency_messages(text))
        if not isinstance(result, DependencyOut):
            result = DependencyOut.model_validate(result.model_dump())
        self.state.open_dependency.pop(sender, None)
        self.last_dependency = result.model_dump(mode="json")
        member = self.state.members.get(sender)
        transfer_to = member.name if member is not None else "the household member"
        person = transfer_to.split()[0]
        plan = revise_plan(
            result,
            line=self.line,
            providers=self.providers,
            transfer_to=transfer_to,
            allowed_recipients=self.allowed_recipients,
        )
        self.state.plan = plan
        self.state.approval_choice = None
        item = next(row for row in plan.items if row.action == "transfer")
        card = build_approval_card(
            recipient=item.recipient,
            account=item.account_label,
            action=item.action_text,
            conditions=item.condition_labels,
            documents=item.documents,
            consequence=item.consequence,
            fallback=item.fallback,
            allowed_recipients=self.allowed_recipients,
        )
        self.state.approval = card
        outs = [
            Outbound(
                sender,
                "Thank you. I've passed that on. Sara approves any change.",
                kind="dependency_ack",
            )
        ]
        owner = self.state.owner_sender
        if owner is not None:
            outs.append(Outbound(owner, render_revision(plan, person), kind="plan_revision"))
            outs.append(
                Outbound(owner, card.text(), options=list(card.options), kind="approval_card")
            )
        return outs

    def _join(self, sender: str, token: str) -> list[Outbound]:
        if token == "":
            return [Outbound(sender, "Hello. If someone invited you, open the invite link again.")]
        invite = self.invites.get(token)
        if invite is None:
            return [Outbound(sender, "That invite isn't valid.", kind="invite_rejected")]
        self.state.members[sender] = MemberRecord(
            sender, invite.name, "household", invite.stated_role
        )
        return [
            Outbound(
                sender,
                f"You're on this case as {invite.name}. "
                f"Stated role: {invite.stated_role} (as the family told us).",
                kind="invite_joined",
            )
        ]

    def _command(self, sender: str, name: str, now: datetime) -> list[Outbound]:
        if self.state.paused and name not in {"resume", "help"}:
            return [Outbound(sender, PAUSED_TEXT, options=[CONTINUE], kind="paused")]
        if name == "resume":
            self.state.paused = False
        if name == "status":
            return [
                Outbound(
                    sender,
                    status_text(self.state.controls, self.snapshot or None),
                    kind="status",
                )
            ]
        reply = apply_command(self.state.controls, name, now)
        return [Outbound(sender, reply, kind=name)]

    def _offer_decision(self, sender: str, text: str) -> list[Outbound]:
        message, options = read_back_decision(text)
        return [Outbound(sender, message, options=list(options), kind="decision_card")]

    def _choose_decision(self, sender: str, button_id: str) -> list[Outbound]:
        if button_id == "see_plan":
            if self.state.plan is None:
                return [Outbound(sender, "The plan isn't ready yet.")]
            person = "Amina"
            owner = self.state.members.get(self.state.owner_sender or "")
            if owner is not None and owner.name:
                person = owner.name.split()[0]
            household = next(
                (member for member in self.state.members.values() if member.role == "household"),
                None,
            )
            if household is not None:
                person = household.name.split()[0]
            return [
                Outbound(sender, render_revision(self.state.plan, person), kind="plan_revision")
            ]
        if self.state.decision_choice is not None:
            return [Outbound(sender, "That's already decided.", kind="already_decided")]
        self.state.decision_choice = button_id
        return [
            Outbound(
                sender,
                "Recorded. I haven't contacted any organisation.",
                kind="decision_recorded",
            )
        ]

    def _approve(self, sender: str) -> list[Outbound]:
        if self.state.approval_choice is not None:
            return [Outbound(sender, "That's already decided.", kind="already_decided")]
        if sender != self.state.owner_sender:
            return [
                Outbound(
                    sender,
                    "Sara approves requests. I haven't sent anything.",
                    kind="approval_refused",
                )
            ]
        if not self.state.controls.org_actions:
            return [
                Outbound(
                    sender,
                    "The case is on hold, so this will not be sent. I haven't contacted anyone.",
                    kind="approval_held",
                )
            ]
        self.state.approval_choice = "approve_plan"
        return [
            Outbound(
                sender,
                "Approved. Nothing is sent until the mail step runs.",
                kind="approval_recorded",
            )
        ]

    def _answer_question(self, text: str) -> str:
        accounts = self.snapshot.get("accounts")
        if isinstance(accounts, list):
            for account in accounts:
                if not isinstance(account, dict):
                    continue
                name = str(account.get("name", ""))
                if name and name.lower() in text.lower():
                    service = account.get("service", "")
                    ownership = account.get("ownership", "unconfirmed")
                    return f"{name}: {service}. Ownership: {ownership}."
        if not self.snapshot:
            return "I can only answer from the case record, and I don't have one loaded yet."
        return "I don't have that in the case record. I won't guess."


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _candidate_from_dict(row: Mapping[str, object]) -> Candidate:
    return Candidate(
        account_ref=str(row.get("account_ref", "")),
        provider=str(row.get("provider", "")),
        service_label=str(row.get("service_label", "")),
        holder_name=str(row.get("holder_name", "")),
        origin=str(row.get("origin", "")),
        ownership=str(row.get("ownership", "unconfirmed")),
        evidence=str(row.get("evidence", "")),
        notes=[str(n) for n in row.get("notes") or []],  # type: ignore[attr-defined]
        track=str(row.get("track", "unknown")),
        evidence_ids=[str(n) for n in row.get("evidence_ids") or []],  # type: ignore[attr-defined]
    )


def _suggestion_to_dict(item: Suggestion) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "text": item.text,
        "why": item.why,
        "target": item.target,
        "status": item.status,
        "options": [{"id": o.id, "label": o.label} for o in item.options],
    }


def _suggestion_from_dict(row: Mapping[str, object]) -> Suggestion:
    return Suggestion(
        id=str(row.get("id", "")),
        kind=str(row.get("kind", "")),
        text=str(row.get("text", "")),
        why=str(row.get("why", "")),
        target=str(row.get("target", "")),
        status=str(row.get("status", "open")),
        options=[
            Option(id=str(o["id"]), label=str(o["label"]))
            for o in row.get("options") or []  # type: ignore[attr-defined]
            if isinstance(o, dict)
        ],
    )


def _plan_to_dict(plan: RevisedPlan | None) -> dict[str, object] | None:
    return asdict(plan) if plan is not None else None


def _plan_from_dict(data: object) -> RevisedPlan | None:
    if not isinstance(data, dict):
        return None
    try:
        items = tuple(
            PlanItem(
                **{
                    **row,
                    "conditions": tuple(row["conditions"]),
                    "condition_labels": tuple(row["condition_labels"]),
                    "documents": tuple(row["documents"]),
                }
            )
            for row in data["items"]
        )
        links = tuple((str(a), str(b)) for a, b in data["links"])
    except (KeyError, TypeError, ValueError):
        return None
    return RevisedPlan(items=items, links=links)


def _approval_to_dict(card: ApprovalCard | None) -> dict[str, object] | None:
    if card is None:
        return None
    return {
        "recipient": card.recipient,
        "account": card.account,
        "action": card.action,
        "conditions": list(card.conditions),
        "documents": list(card.documents),
        "consequence": card.consequence,
        "fallback": card.fallback,
    }


def _approval_from_dict(data: object) -> ApprovalCard | None:
    if not isinstance(data, dict):
        return None
    try:
        return ApprovalCard(
            recipient=str(data["recipient"]),
            account=str(data["account"]),
            action=str(data["action"]),
            conditions=tuple(data["conditions"]),
            documents=tuple(data["documents"]),
            consequence=str(data["consequence"]),
            fallback=str(data["fallback"]),
        )
    except (KeyError, TypeError):
        return None
