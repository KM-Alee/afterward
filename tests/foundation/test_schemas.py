"""Strict AI schemas reject extra fields and do not include an accept action."""

import pytest
from pydantic import ValidationError

from app.ai import schemas
from app.ai.schemas import (
    CALL_TOOL_SCHEMAS,
    CommitmentOut,
    Fact,
    ReplyOut,
    RequestFamilyDecisionArgs,
)


def test_call_turn_out_was_replaced():
    assert not hasattr(schemas, "CallTurnOut")
    assert "accept" not in CALL_TOOL_SCHEMAS
    assert set(CALL_TOOL_SCHEMAS) == {
        "report_offered_terms",
        "request_family_decision",
        "request_human_help",
        "end_call",
    }


def test_reply_schema_rejects_extra_and_requires_nulls():
    payload = {
        "commitments": [
            {
                "account_hint": "line ending 4417",
                "action": "transfer",
                "status": "completed",
                "negated": False,
                "conditions_or_requirements": ["voicemail will be reset"],
                "facts": [
                    {
                        "key": "voicemail_preserved",
                        "value": "false",
                        "evidence_quote": "Voicemail will be reset",
                    }
                ],
                "scope": "this_service",
                "effective_date": None,
                "evidence_quote": "Request complete.",
                "interpretation": "clear",
            }
        ],
        "asks_for_documents": [],
        "is_marketing_to_deceased": False,
    }
    reply = ReplyOut.model_validate(payload)
    assert reply.commitments[0].facts[0].key == "voicemail_preserved"
    with pytest.raises(ValidationError):
        ReplyOut.model_validate({**payload, "recipient": "injected@example.com"})
    with pytest.raises(ValidationError):
        CommitmentOut.model_validate({**payload["commitments"][0], "effective_date": ...})


def test_family_decision_options_are_capped():
    with pytest.raises(ValidationError):
        RequestFamilyDecisionArgs(summary="New terms", options=["a", "b", "c", "d"])
    Fact(key="number_kept", value="true", evidence_quote="the number is kept")
