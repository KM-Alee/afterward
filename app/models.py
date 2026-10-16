"""PostgreSQL tables for contract revision 1.

`cases` is the case itself, so it has no `case_id`. `provider_profiles` and
`proof_runs` are global. Every other product table carries `case_id`.
Enum values are stored as strings so isolated test schemas do not share
database enum types.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared metadata for the product schema."""


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=64,
        values_callable=lambda cls: [item.value for item in cls],
    )


class TimestampMixin:
    """Creation and update times on every product table."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Autopilot(StrEnum):
    gentle = "gentle"
    steady = "steady"


class CaseControl(StrEnum):
    active = "active"
    quiet_until = "quiet_until"
    hold = "hold"
    stopped = "stopped"


class Monitoring(StrEnum):
    ok = "ok"
    interrupted = "interrupted"


class MemberRole(StrEnum):
    owner = "owner"
    household = "household"


class ChannelName(StrEnum):
    telegram = "telegram"
    whatsapp = "whatsapp"
    web = "web"


class AccountOrigin(StrEnum):
    forwarded = "forwarded"
    photo = "photo"
    manual = "manual"
    inbox = "inbox"


class Ownership(StrEnum):
    unconfirmed = "unconfirmed"
    confirmed = "confirmed"
    not_theirs = "not_theirs"


class ServiceStatus(StrEnum):
    active = "active"
    requested = "requested"
    acknowledged = "acknowledged"
    blocked = "blocked"
    closed = "closed"
    transferred = "transferred"
    frozen = "frozen"


class MoneyStatus(StrEnum):
    none = "none"
    needs_review = "needs_review"
    likely_error = "likely_error"
    refund_promised = "refund_promised"
    issued_awaiting_receipt = "issued_awaiting_receipt"
    received = "received"
    balance_owed = "balance_owed"
    dispute_open = "dispute_open"


class DocsStatus(StrEnum):
    none_needed = "none_needed"
    requested = "requested"
    requirement_unmet = "requirement_unmet"
    sent = "sent"
    accepted = "accepted"


class DependencyKind(StrEnum):
    shared_service = "shared_service"
    access = "access"
    evidence = "evidence"
    memory = "memory"


class PlanAction(StrEnum):
    close = "close"
    transfer = "transfer"
    freeze = "freeze"
    refund = "refund"
    notify = "notify"
    document_request = "document_request"
    contract_change = "contract_change"
    service_change = "service_change"
    other = "other"


class PlanStatus(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    superseded = "superseded"


class ApprovalStatus(StrEnum):
    open = "open"
    approved = "approved"
    declined = "declined"
    void = "void"


class DocumentForm(StrEnum):
    photo = "photo"
    scan = "scan"
    certified_copy_held = "certified_copy_held"
    original_held = "original_held"


class MessageDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class RecipientCheck(StrEnum):
    approved = "approved"
    unapproved = "unapproved"
    reply_to_mismatch = "reply_to_mismatch"


class CommitmentStatus(StrEnum):
    requested = "requested"
    acknowledged = "acknowledged"
    promised = "promised"
    conditional = "conditional"
    blocked = "blocked"
    refused = "refused"
    completed = "completed"


class CommitmentScope(StrEnum):
    this_service = "this_service"
    all_services = "all_services"
    unclear = "unclear"


class Interpretation(StrEnum):
    clear = "clear"
    ambiguous = "ambiguous"


class MoneyKind(StrEnum):
    charge = "charge"
    refund = "refund"
    balance = "balance"


class MoneyItemStatus(StrEnum):
    needs_review = "needs_review"
    likely_error = "likely_error"
    refund_promised = "refund_promised"
    issued_awaiting_receipt = "issued_awaiting_receipt"
    received = "received"
    balance_owed = "balance_owed"


class DeadlineStatus(StrEnum):
    potentially_relevant = "potentially_relevant"
    eligibility_incomplete = "eligibility_incomplete"
    deadline_confirmed = "deadline_confirmed"
    claimed = "claimed"
    expired = "expired"


class DecisionStatus(StrEnum):
    open = "open"
    chosen = "chosen"
    void = "void"


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    cancelled = "cancelled"
    succeeded = "succeeded"
    failed = "failed"


class ActionStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    uncertain = "uncertain"
    failed = "failed"
    reconciled = "reconciled"


class Case(TimestampMixin, Base):
    """One bereavement administration case. The primary key is the case id."""

    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(
            "clock_offset_s = 0 OR is_demo",
            name="ck_cases_clock_offset_demo_only",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    deceased_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_death: Mapped[date | None] = mapped_column(Date)
    intent_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    autopilot: Mapped[Autopilot] = mapped_column(
        _enum(Autopilot, "case_autopilot"), nullable=False, default=Autopilot.gentle
    )
    control: Mapped[CaseControl] = mapped_column(
        _enum(CaseControl, "case_control"), nullable=False, default=CaseControl.active
    )
    quiet_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_during_quiet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monitoring: Mapped[Monitoring] = mapped_column(
        _enum(Monitoring, "case_monitoring"), nullable=False, default=Monitoring.ok
    )
    clock_offset_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Member(TimestampMixin, Base):
    """A person on the case. Roles are stated, never verified."""

    __tablename__ = "members"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[MemberRole] = mapped_column(_enum(MemberRole, "member_role"), nullable=False)
    stated_role_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    channel: Mapped[ChannelName] = mapped_column(
        _enum(ChannelName, "member_channel"), nullable=False
    )
    channel_user_id: Mapped[str | None] = mapped_column(String(128))
    consent: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ProviderProfile(TimestampMixin, Base):
    """Declared organisation facts. Global: profiles are not owned by one case."""

    __tablename__ = "provider_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    accepted_channels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_info: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_docs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    response_window_bd: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    approved_recipients: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Account(TimestampMixin, Base):
    """A candidate or confirmed account. Same `account_ref` in a case is one account."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("case_id", "account_ref", name="uq_accounts_case_ref"),
        Index("ix_accounts_case", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_profiles.id", ondelete="SET NULL")
    )
    account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    service_label: Mapped[str] = mapped_column(String(200), nullable=False)
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    origin: Mapped[AccountOrigin] = mapped_column(
        _enum(AccountOrigin, "account_origin"), nullable=False
    )
    origin_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ownership: Mapped[Ownership] = mapped_column(
        _enum(Ownership, "account_ownership"), nullable=False, default=Ownership.unconfirmed
    )
    status_service: Mapped[ServiceStatus] = mapped_column(
        _enum(ServiceStatus, "account_status_service"), nullable=False, default=ServiceStatus.active
    )
    status_money: Mapped[MoneyStatus] = mapped_column(
        _enum(MoneyStatus, "account_status_money"), nullable=False, default=MoneyStatus.none
    )
    status_docs: Mapped[DocsStatus] = mapped_column(
        _enum(DocsStatus, "account_status_docs"), nullable=False, default=DocsStatus.none_needed
    )
    next_step: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Dependency(TimestampMixin, Base):
    """A fact only a person can supply, and any account it links to."""

    __tablename__ = "dependencies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[DependencyKind] = mapped_column(
        _enum(DependencyKind, "dependency_kind"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_member_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL")
    )
    linked_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL")
    )


class Plan(TimestampMixin, Base):
    """One immutable plan version. A change inserts a new row and a new hash."""

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("account_id", "version", name="uq_plans_account_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[PlanAction] = mapped_column(_enum(PlanAction, "plan_action"), nullable=False)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    documents_to_disclose: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    fallback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus, "plan_status"), nullable=False, default=PlanStatus.draft
    )
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class Approval(TimestampMixin, Base):
    """An approval bound to one plan id, version and hash."""

    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_plan", "plan_id", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    member_id: Mapped[UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    card: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ApprovalStatus] = mapped_column(
        _enum(ApprovalStatus, "approval_status"), nullable=False, default=ApprovalStatus.open
    )


class Document(TimestampMixin, Base):
    """A vault document. `blob` is Fernet ciphertext, never plaintext."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(120), nullable=False)
    form: Mapped[DocumentForm] = mapped_column(_enum(DocumentForm, "document_form"), nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mismatch_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    sha256: Mapped[str | None] = mapped_column(String(64))


class Message(TimestampMixin, Base):
    """Latest text and a hash. Full mailbox bodies are not stored."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread", "case_id", "thread_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[MessageDirection] = mapped_column(
        _enum(MessageDirection, "message_direction"), nullable=False
    )
    gmail_id: Mapped[str | None] = mapped_column(String(128))
    thread_id: Mapped[str | None] = mapped_column(String(128))
    rfc_message_id: Mapped[str | None] = mapped_column(String(256))
    from_addr: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    reply_to: Mapped[str | None] = mapped_column(String(320))
    to_addrs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    latest_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    full_text_sha256: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_check: Mapped[RecipientCheck | None] = mapped_column(
        _enum(RecipientCheck, "message_recipient_check")
    )


class Commitment(TimestampMixin, Base):
    """One structured commitment extracted from a message."""

    __tablename__ = "commitments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    action: Mapped[PlanAction] = mapped_column(
        _enum(PlanAction, "commitment_action"), nullable=False
    )
    status: Mapped[CommitmentStatus] = mapped_column(
        _enum(CommitmentStatus, "commitment_status"), nullable=False
    )
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    facts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    negated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scope: Mapped[CommitmentScope] = mapped_column(
        _enum(CommitmentScope, "commitment_scope"), nullable=False
    )
    effective_date: Mapped[str | None] = mapped_column(String(32))
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interpretation: Mapped[Interpretation] = mapped_column(
        _enum(Interpretation, "commitment_interpretation"),
        nullable=False,
        default=Interpretation.ambiguous,
    )


class OutcomeCheck(TimestampMixin, Base):
    """Deterministic comparison of a plan version with commitment records."""

    __tablename__ = "outcome_checks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)


class MoneyItem(TimestampMixin, Base):
    """A charge, refund or balance with an explicit money status."""

    __tablename__ = "money_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MoneyKind] = mapped_column(_enum(MoneyKind, "money_kind"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    service_period_start: Mapped[date | None] = mapped_column(Date)
    service_period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MoneyItemStatus] = mapped_column(
        _enum(MoneyItemStatus, "money_item_status"), nullable=False
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Deadline(TimestampMixin, Base):
    """A possibly relevant deadline. Stretch data, still part of the schema."""

    __tablename__ = "deadlines"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[DeadlineStatus] = mapped_column(
        _enum(DeadlineStatus, "deadline_status"), nullable=False
    )
    missing_facts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    due_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Decision(TimestampMixin, Base):
    """A family decision rendered as at most three buttons."""

    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[DecisionStatus] = mapped_column(
        _enum(DecisionStatus, "decision_status"), nullable=False, default=DecisionStatus.open
    )
    chosen: Mapped[str | None] = mapped_column(String(64))


class Job(TimestampMixin, Base):
    """A durable unit of work. `idem_key` is unique. Leases use wall-clock time."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("idem_key", name="uq_jobs_idem_key"),
        Index("ix_jobs_due", "status", "run_at_case_time"),
        CheckConstraint("length(idem_key) > 0", name="ck_jobs_idem_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    run_at_case_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), nullable=False, default=JobStatus.pending
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    idem_key: Mapped[str] = mapped_column(String(200), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(200))


class Action(TimestampMixin, Base):
    """An outbound effect. Uncertain delivery is reconciled, not blindly retried."""

    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("idem_key", name="uq_actions_idem_key"),
        CheckConstraint("length(idem_key) > 0", name="ck_actions_idem_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    idem_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(
        _enum(ActionStatus, "action_status"), nullable=False, default=ActionStatus.pending
    )
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    external_id: Mapped[str | None] = mapped_column(String(256))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Event(TimestampMixin, Base):
    """Append-only audit row. Payloads must not carry secrets or document bodies."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_case_ts", "case_id", "ts"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Latency(TimestampMixin, Base):
    """Measured call-turn timings. Reported, never claimed in advance."""

    __tablename__ = "latency"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_timings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    client_total_ms: Mapped[int | None] = mapped_column(Integer)


class ProofRun(TimestampMixin, Base):
    """Proof-panel history. Global: a run is not a single case row."""

    __tablename__ = "proof_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


def _remember_new_cases() -> None:
    from sqlalchemy import event as sa_event

    from app.conversation.case_link import remember_case

    sa_event.listen(Case, "init", lambda target, _args, _kwargs: remember_case(target))


_remember_new_cases()
