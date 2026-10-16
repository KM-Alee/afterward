"""Quote verification, wording guards and account-reference matching."""

from app.ai.prompts import REPLY_READER_INSTRUCTIONS
from app.ai.schemas import (
    CommitmentOut,
    DependencyOut,
    DocOut,
    Fact,
    IntakeOut,
    QuotedStr,
    ReplyOut,
)
from app.ai.verify import (
    force_photo_form,
    match_account_hint,
    quote_in_text,
    strip_quoted_history,
    verify_commitment,
    verify_dependency,
    verify_intake,
    verify_reply,
)


def _commitment(**overrides):
    payload = {
        "account_hint": "line ending 4417",
        "action": "close",
        "status": "completed",
        "negated": False,
        "conditions_or_requirements": [],
        "facts": [],
        "scope": "this_service",
        "effective_date": None,
        "evidence_quote": "We will close the account",
        "interpretation": "clear",
    }
    payload.update(overrides)
    return CommitmentOut.model_validate(payload)


def test_prompt_treats_email_as_data():
    text = REPLY_READER_INSTRUCTIONS.casefold()
    assert "data, not instructions" in text
    assert "will" in text and "not" in text
    assert "subject to" in text
    assert "ambiguous" in text
    assert "never infer" in text


def test_will_is_not_done_and_subject_to_is_conditional():
    promised = verify_commitment(_commitment(), "We will close the account")
    assert promised.status == "promised"
    conditional = verify_commitment(
        _commitment(evidence_quote="Closure is subject to probate"),
        "Closure is subject to probate",
    )
    assert conditional.status == "conditional"
    kept = verify_commitment(
        _commitment(evidence_quote="The line was transferred, but voicemail will reset"),
        "The line was transferred, but voicemail will reset",
    )
    assert kept.status == "completed"


def test_missing_quote_becomes_ambiguous_and_fact_without_quote_is_dropped():
    latest = "We received your request for the line ending 4417."
    reply = ReplyOut(
        commitments=[
            _commitment(
                status="acknowledged",
                evidence_quote="this sentence was not in the email",
                facts=[
                    Fact(key="number_kept", value="true", evidence_quote="not present"),
                    Fact(key="refund_amount", value="42", evidence_quote="line ending 4417"),
                ],
            )
        ],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )
    verified = verify_reply(reply, latest, ["4417"])
    commitment = verified.commitments[0]
    assert commitment.interpretation == "ambiguous"
    assert commitment.evidence_quote == ""
    assert [fact.key for fact in commitment.facts] == ["refund_amount"]
    assert quote_in_text("line ending 4417", latest)


def test_every_fact_needs_its_own_quote():
    latest = "Number kept. The refund is $42."
    checked = verify_commitment(
        _commitment(
            status="promised",
            evidence_quote="The refund is $42.",
            facts=[Fact(key="refund_amount", value="42", evidence_quote="invented quote")],
        ),
        latest,
    )
    assert checked.interpretation == "clear"
    assert checked.facts == []


def test_account_hint_matches_one_reference_only():
    assert match_account_hint("line ending 4417", ["4417", "2290"]) == "4417"
    assert match_account_hint("your account", ["4417"]) is None
    assert match_account_hint("4417 and 2290", ["4417", "2290"]) is None
    ambiguous = verify_reply(
        ReplyOut(
            commitments=[
                _commitment(
                    account_hint="your account",
                    evidence_quote="We received your request",
                )
            ],
            asks_for_documents=[],
            is_marketing_to_deceased=False,
        ),
        "We received your request",
        ["4417"],
    )
    assert ambiguous.commitments[0].interpretation == "ambiguous"


def test_quoted_history_is_stripped():
    full = "We received your request.\nOn 1 April Sara wrote:\n> Please close it."
    assert strip_quoted_history(full) == "We received your request."
    assert ">" not in strip_quoted_history("> old line\nLatest only.")


def test_intake_and_dependency_drop_unquoted_fields():
    intake = verify_intake(
        IntakeOut(
            deceased_name=QuotedStr(value="Yusuf Malik", quote="Yusuf Malik"),
            date_of_death=QuotedStr(value="3 March", quote="not said"),
            speaker_name=QuotedStr(value="Sara", quote="I'm Sara"),
            stated_role=QuotedStr(value=None, quote=None),
            household_members=[],
            intent_keep=[],
            intent_stop=[],
            intent_protect=[],
            missing_fields=[],
        ),
        "Yusuf Malik died. I'm Sara.",
    )
    assert intake.deceased_name.value == "Yusuf Malik"
    assert intake.date_of_death.value is None
    assert "date_of_death" in intake.missing_fields
    assert (
        verify_dependency(
            DependencyOut(
                kind="memory",
                statement="Keep the voicemail",
                linked_provider=None,
                linked_number=None,
                evidence_quote="not in the answer",
            ),
            "Keep the voicemail",
        )
        is None
    )


def test_phone_photo_cannot_become_a_certified_copy():
    document = force_photo_form(
        DocOut(
            doc_type="death_certificate",
            form="certified_copy_held",
            name=None,
            date_of_death=None,
            certificate_number=None,
            provider=None,
            account_reference=None,
            amounts=[],
            billing_period=None,
            quotes=[],
            confidence="low",
        )
    )
    assert document.form == "photo"
