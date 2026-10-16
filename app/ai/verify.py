"""Quote checks. Missing quotes are dropped and the item becomes ambiguous."""

from __future__ import annotations

import re

from app.ai.schemas import (
    CommitmentOut,
    DependencyOut,
    DocOut,
    IntakeOut,
    QuotedStr,
    ReplyOut,
)

_WILL = re.compile(r"\bwill\b", re.IGNORECASE)
_FUTURE_DONE = re.compile(
    r"\bwill\b(?:\s+\w+){0,4}\s+(?:be\s+)?"
    r"(?:completed|complete|closed|transferred|issued|received|cancelled|canceled)\b",
    re.IGNORECASE,
)
_SUBJECT_TO = re.compile(r"subject to", re.IGNORECASE)
_COMPLETION = re.compile(
    r"\b(completed|complete|transferred|closed|issued|received|cancelled|canceled)\b",
    re.IGNORECASE,
)
_ON_WROTE = re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE)


def normalise_text(value: str) -> str:
    """Case-fold and collapse whitespace so a quote can be found in the latest text."""
    return " ".join(value.casefold().split())


def quote_in_text(quote: str, latest_text: str) -> bool:
    """True only when the quote itself occurs in the latest text."""
    if not quote or not quote.strip():
        return False
    return normalise_text(quote) in normalise_text(latest_text)


def strip_quoted_history(full_text: str) -> str:
    """Keep the latest reply. Drop quoted lines and everything from an 'On ... wrote:' marker."""
    kept: list[str] = []
    for line in full_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if _ON_WROTE.match(stripped) or stripped.startswith("-----Original Message-----"):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def match_account_hint(hint: str, account_refs: list[str]) -> str | None:
    """Return the single case account reference named by the hint. Zero or many is no match."""
    matches = [
        ref
        for ref in account_refs
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(ref)}(?![A-Za-z0-9])", hint, re.IGNORECASE)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def apply_wording_guards(commitment: CommitmentOut) -> CommitmentOut:
    """'will' is not done, and 'subject to' is conditional, even if the model says completed."""
    quote = commitment.evidence_quote
    status = commitment.status
    if status == "completed" and (
        _FUTURE_DONE.search(quote) or (_WILL.search(quote) and not _COMPLETION.search(quote))
    ):
        status = "promised"
    if _SUBJECT_TO.search(quote) and status in {"completed", "promised", "acknowledged"}:
        status = "conditional"
    if status == commitment.status:
        return commitment
    return commitment.model_copy(update={"status": status})


def verify_commitment(commitment: CommitmentOut, latest_text: str) -> CommitmentOut:
    """Drop the commitment quote and any fact whose own quote is absent. Absent means ambiguous."""
    checked = apply_wording_guards(commitment)
    quote_ok = quote_in_text(checked.evidence_quote, latest_text)
    facts = [fact for fact in checked.facts if quote_in_text(fact.evidence_quote, latest_text)]
    if quote_ok:
        return checked.model_copy(update={"facts": facts})
    return checked.model_copy(
        update={"facts": facts, "evidence_quote": "", "interpretation": "ambiguous"}
    )


def verify_reply(reply: ReplyOut, latest_text: str, account_refs: list[str]) -> ReplyOut:
    """Verify every commitment. The matched account ref is not written back into the hint."""
    commitments = []
    for commitment in reply.commitments:
        verified = verify_commitment(commitment, latest_text)
        matched = match_account_hint(verified.account_hint, account_refs)
        if matched is None and verified.interpretation == "clear":
            verified = verified.model_copy(update={"interpretation": "ambiguous"})
        commitments.append(verified)
    return reply.model_copy(update={"commitments": commitments})


def verify_quoted_field(field: QuotedStr, transcript: str) -> QuotedStr:
    """A field without a quote that occurs in the transcript is missing."""
    if field.quote and quote_in_text(field.quote, transcript) and field.value:
        return field
    return QuotedStr(value=None, quote=None)


def verify_intake(intake: IntakeOut, transcript: str) -> IntakeOut:
    """Drop intake fields whose quotes are not in the transcript and list them as missing."""
    fields = {
        "deceased_name": verify_quoted_field(intake.deceased_name, transcript),
        "date_of_death": verify_quoted_field(intake.date_of_death, transcript),
        "speaker_name": verify_quoted_field(intake.speaker_name, transcript),
        "stated_role": verify_quoted_field(intake.stated_role, transcript),
    }
    missing = list(intake.missing_fields)
    for name, field in fields.items():
        if field.value is None and name not in missing:
            missing.append(name)
    members = []
    for member in intake.household_members:
        if member.quote and quote_in_text(member.quote, transcript):
            members.append(member)
    lists = {}
    for name in ("intent_keep", "intent_stop", "intent_protect"):
        kept = []
        for item in getattr(intake, name):
            if item.quote and quote_in_text(item.quote, transcript):
                kept.append(item)
        lists[name] = kept
    return intake.model_copy(
        update={**fields, **lists, "household_members": members, "missing_fields": missing}
    )


def verify_dependency(dependency: DependencyOut, text: str) -> DependencyOut | None:
    """A dependency whose quote is not in the answer is not applied."""
    if quote_in_text(dependency.evidence_quote, text):
        return dependency
    return None


def force_photo_form(document: DocOut) -> DocOut:
    """A phone photo is always a photo. The model cannot upgrade it to a certified copy."""
    if document.form == "photo":
        return document
    return document.model_copy(update={"form": "photo"})
