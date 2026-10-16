"""Sara's voice note through the Northline approval card, on fakes."""

import pytest

from app.contracts import Channel
from app.conversation.demo_malik import (
    AMINA_SCRIPT,
    SARA_SCRIPT,
    run_malik_script,
)
from app.fakes import FakeAI, FakeChannel


@pytest.mark.asyncio
async def test_scripted_malik_conversation():
    ai = FakeAI()
    channel = FakeChannel()
    assert isinstance(channel, Channel)
    result = await run_malik_script(ai, channel)
    state = result.conversation.state
    sent_text = "\n".join(item.text for item in result.sent)

    intake = next(item for item in result.sent if item.kind == "intake_card")
    assert "Yusuf Malik" in intake.text
    assert "3 March 2026" in intake.text
    assert "Stated role" in intake.text
    assert "as you've told me" in intake.text
    assert "verified" not in intake.text.lower()
    assert "executor" not in intake.text.lower()
    assert "Mum's phone" in intake.text
    assert "Dad's voicemail" in intake.text
    assert state.intake_confirmed is True
    assert state.members["1001"].role == "owner"
    assert state.members["1001"].stated_role == "his daughter, sorting things out"

    coverage = next(item for item in result.sent if item.kind == "coverage")
    assert state.coverage is not None
    assert len(state.candidates) == 9
    assert {item.account_ref for item in state.candidates} == {
        "4417",
        "2290",
        "0932",
        "CP-77120",
        "SB-88213",
        "FL-5531",
        "HW-20418",
        "ML-6610",
        "PB-3017",
    }
    assert sum(item.account_ref == "4417" for item in state.candidates) == 1
    northline = next(item for item in state.candidates if item.account_ref == "4417")
    assert "Northline bill" in northline.evidence
    assert "Northline receipt" in northline.evidence
    assert len(state.coverage.unconfirmed) == 3
    assert "6 emails" in coverage.text
    assert "4 photos" in coverage.text
    assert "9 possible accounts" in coverage.text
    assert "3 need you to confirm" in coverage.text
    assert "looks complete" not in coverage.text.lower()
    assert "Yusuf's own inbox" in state.coverage.not_searched[0]
    assert state.coverage.where_else

    joined = next(item for item in result.sent if item.kind == "invite_joined")
    assert state.members["2002"].role == "household"
    assert state.members["2002"].name == "Amina Malik"
    assert "Stated role" in joined.text
    assert "verified" not in joined.text.lower()

    question = next(item for item in result.sent if item.kind == "dependency_question")
    assert "4417" in question.text
    assert "Northline Mobile" in question.text

    assert state.plan is not None
    revision = next(item for item in result.sent if item.kind == "plan_revision")
    assert "transfer to Amina" in revision.text
    assert "don't close" in revision.text
    assert "Crescent Bank" in revision.text
    transfer = next(item for item in state.plan.items if item.action == "transfer")
    assert transfer.recipient == "bereavement@northline.example"
    assert transfer.conditions == ("number_kept", "voicemail_preserved", "no_new_contract")
    assert ("4417", "0932") in state.plan.links
    assert AMINA_SCRIPT not in transfer.recipient

    card = next(item for item in result.sent if item.kind == "approval_card")
    assert state.approval is not None
    assert state.approval.recipient == "bereavement@northline.example"
    assert "transfer to Amina Malik" in card.text
    assert "death certificate (photo)" in card.text
    assert "keep the voicemail" in card.text
    assert card.options is not None
    assert len(card.options) <= 3
    assert all(len(option.label) <= 20 for option in card.options)
    assert "intruder@" not in card.text

    photo = next(
        item for item in state.vault_items if item.fields["account_reference"] == "ML-6610"
    )
    assert photo.form == "photo"
    assert "form_overridden_photo" in photo.mismatch_flags
    assert b"FICTIONAL-DEMO-PHOTO-ML-6610" not in photo.blob
    assert result.cipher.decrypt(photo.blob) == b"FICTIONAL-DEMO-PHOTO-ML-6610"
    assert result.cipher.generated is True

    buttons = [message for message in channel.outbox if message["kind"] == "buttons"]
    assert any(
        message["to"] == "1001" and "Approve" in str(message["options"]) for message in buttons
    )
    assert "Yusuf Malik" in sent_text
    assert SARA_SCRIPT.startswith("My dad, Yusuf Malik")
