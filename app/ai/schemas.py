"""Strict model-output schemas. Extra fields are rejected. Nulls are explicit.

`CallTurnOut` is not part of this contract. Provider calls use the realtime
tool argument models below. None of them is an acceptance.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STRICT = ConfigDict(extra="forbid")

FactKey = Literal[
    "number_kept",
    "voicemail_preserved",
    "contract_months",
    "monthly_price",
    "new_holder",
    "refund_amount",
    "service_period_start",
    "service_period_end",
    "document_required",
    "document_form",
]

CommitmentAction = Literal[
    "close",
    "transfer",
    "freeze",
    "refund",
    "notify",
    "document_request",
    "contract_change",
    "service_change",
    "other",
]

CommitmentState = Literal[
    "requested",
    "acknowledged",
    "promised",
    "conditional",
    "blocked",
    "refused",
    "completed",
]


class QuotedStr(BaseModel):
    """A value taken from the family's words, with the quote that supports it."""

    model_config = STRICT

    value: str | None
    quote: str | None


class HouseholdMemberOut(BaseModel):
    """Someone the speaker named. The relationship is stated, not verified."""

    model_config = STRICT

    name: str | None
    relationship: str | None
    quote: str | None


class IntakeOut(BaseModel):
    """Tell-it-once extraction. Missing facts stay null and are listed."""

    model_config = STRICT

    deceased_name: QuotedStr
    date_of_death: QuotedStr
    speaker_name: QuotedStr
    stated_role: QuotedStr
    household_members: list[HouseholdMemberOut]
    intent_keep: list[QuotedStr]
    intent_stop: list[QuotedStr]
    intent_protect: list[QuotedStr]
    missing_fields: list[str]


class DependencyOut(BaseModel):
    """A dependency answer. Code, not this model, turns it into plan conditions."""

    model_config = STRICT

    kind: Literal["shared_service", "access", "evidence", "memory"]
    statement: str
    linked_provider: str | None
    linked_number: str | None
    evidence_quote: str


class DocOut(BaseModel):
    """Vision extraction. A phone photo is still forced to `photo` by code."""

    model_config = STRICT

    doc_type: str
    form: Literal["photo", "scan", "certified_copy_held", "original_held"]
    name: str | None
    date_of_death: str | None
    certificate_number: str | None
    provider: str | None
    account_reference: str | None
    amounts: list[str]
    billing_period: str | None
    quotes: list[str]
    confidence: Literal["low", "high"]


class DocRequest(BaseModel):
    """A document ask found in an untrusted reply. The recipient is not approved."""

    model_config = STRICT

    document_type: str
    required_form: Literal["photo", "scan", "certified_copy", "original"]
    recipient_mentioned: str | None


class Fact(BaseModel):
    """One typed fact from the latest text, with its own quote."""

    model_config = STRICT

    key: FactKey
    value: str
    evidence_quote: str


class CommitmentOut(BaseModel):
    """One commitment. `will` is not `completed`. Unsure means `ambiguous`."""

    model_config = STRICT

    account_hint: str
    action: CommitmentAction
    status: CommitmentState
    negated: bool
    conditions_or_requirements: list[str]
    facts: list[Fact]
    scope: Literal["this_service", "all_services", "unclear"]
    effective_date: str | None
    evidence_quote: str
    interpretation: Literal["clear", "ambiguous"]


class ReplyOut(BaseModel):
    """Structured reading of one provider reply. It grants nothing."""

    model_config = STRICT

    commitments: list[CommitmentOut]
    asks_for_documents: list[DocRequest]
    is_marketing_to_deceased: bool


class ReportOfferedTermsArgs(BaseModel):
    """Facts a representative offered. Quotes are required. This does not accept."""

    model_config = STRICT

    facts: list[Fact]


class RequestFamilyDecisionArgs(BaseModel):
    """Ask the family. At most three options. Acceptance is not one of them."""

    model_config = STRICT

    summary: str
    options: list[str] = Field(max_length=3)


class RequestHumanHelpArgs(BaseModel):
    """The organisation will not deal with the assistant."""

    model_config = STRICT

    reason: str


class EndCallArgs(BaseModel):
    """End the call without agreeing to terms."""

    model_config = STRICT

    reason: str


CALL_TOOL_SCHEMAS = {
    "report_offered_terms": ReportOfferedTermsArgs,
    "request_family_decision": RequestFamilyDecisionArgs,
    "request_human_help": RequestHumanHelpArgs,
    "end_call": EndCallArgs,
}
