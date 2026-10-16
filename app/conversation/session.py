"""Family conversation. Buttons confirm choices; model output cannot add a recipient."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

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
from app.discovery.candidates import Candidate, confirm_candidate, ingest_email, ingest_photo
from app.discovery.coverage import Coverage, coverage_panel, render_coverage
from app.discovery.vault import VaultCipher, VaultItem, intake_document

VOICE_PROMPT = "Bereavement administration. The speaker may mention Yusuf Malik, Sara or Amina."
VOICE_KEYWORDS = ("Yusuf Malik", "Sara", "Amina", "Northline", "Crescent")
DECLINE = (
    "I can only help with the admin after a death: accounts, documents, "
    "and what the family asked us to do."
)
STOPPED = "The case is stopped, including monitoring. Say resume when you want to continue."
_DECISION_IDS = frozenset({"keep_line", "close_line", "hold_safe", "not_now", "see_plan"})


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
            return [
                Outbound(sender, "Thank you. I've saved that summary.", kind="intake_confirmed")
            ]
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
        return [Outbound(sender, "I don't have that button on the current card.")]

    def ask_dependency(self, sender: str) -> list[Outbound]:
        """Ask the household member about the line before anything changes."""
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
