"""A reply with a made-up quote is read again once, then checked."""

import pytest

from app.ai.schemas import ReplyOut
from app.contracts import ChatMessage
from app.engine.pipeline import extract_verified_reply

LATEST = "Request complete. Voicemail will be reset during migration."


def _reply(quote: str, interpretation: str = "clear", hint: str = "line ending 4417") -> ReplyOut:
    return ReplyOut.model_validate(
        {
            "commitments": [
                {
                    "account_hint": hint,
                    "action": "transfer",
                    "status": "completed",
                    "negated": False,
                    "conditions_or_requirements": [],
                    "facts": [
                        {
                            "key": "voicemail_preserved",
                            "value": "false",
                            "evidence_quote": quote,
                        }
                    ],
                    "scope": "this_service",
                    "effective_date": None,
                    "evidence_quote": quote,
                    "interpretation": interpretation,
                }
            ],
            "asks_for_documents": [],
            "is_marketing_to_deceased": False,
        }
    )


class _TwoReads:
    def __init__(self) -> None:
        self.calls = 0

    async def structured(self, role, schema, messages, images=None):
        del role, schema, images
        self.calls += 1
        if self.calls == 1:
            return _reply("not in the email")
        assert any(
            isinstance(item, ChatMessage) and "exact copies" in item.content for item in messages
        )
        return _reply("Voicemail will be reset during migration.")


@pytest.mark.asyncio
async def test_bad_quote_is_read_again_and_then_kept():
    reader = _TwoReads()
    verified = await extract_verified_reply(reader, LATEST, ["4417"])
    assert reader.calls == 2
    assert verified.commitments[0].interpretation == "clear"
    assert verified.commitments[0].evidence_quote == "Voicemail will be reset during migration."


class _OneRead:
    def __init__(self, reply: ReplyOut) -> None:
        self.reply = reply

    async def structured(self, role, schema, messages, images=None):
        del role, schema, messages, images
        return self.reply


QUOTE = "Voicemail will be reset during migration."


@pytest.mark.asyncio
async def test_hint_without_a_number_takes_the_routed_thread_account():
    reader = _OneRead(_reply(QUOTE, hint="Line"))
    verified = await extract_verified_reply(reader, LATEST, ["4417", "2290"], thread_ref="4417")
    assert verified.commitments[0].interpretation == "clear"
    assert verified.commitments[0].account_hint == "4417"


@pytest.mark.asyncio
async def test_hint_without_a_number_and_no_thread_stays_ambiguous():
    reader = _OneRead(_reply(QUOTE, hint="Line"))
    verified = await extract_verified_reply(reader, LATEST, ["4417"])
    assert verified.commitments[0].interpretation == "ambiguous"


@pytest.mark.asyncio
async def test_hint_naming_another_number_is_not_rebound_to_the_thread():
    reader = _OneRead(_reply(QUOTE, hint="line ending 9999"))
    verified = await extract_verified_reply(reader, LATEST, ["4417"], thread_ref="4417")
    assert verified.commitments[0].account_hint == "line ending 9999"
    assert verified.commitments[0].interpretation == "ambiguous"


@pytest.mark.asyncio
async def test_hint_naming_a_different_case_account_keeps_that_account():
    reader = _OneRead(_reply(QUOTE, hint="line ending 2290"))
    verified = await extract_verified_reply(reader, LATEST, ["4417", "2290"], thread_ref="4417")
    assert verified.commitments[0].account_hint == "line ending 2290"


@pytest.mark.asyncio
async def test_thread_does_not_upgrade_an_ambiguous_reading():
    reader = _OneRead(_reply(QUOTE, interpretation="ambiguous", hint="Line"))
    verified = await extract_verified_reply(reader, LATEST, ["4417"], thread_ref="4417")
    assert verified.commitments[0].interpretation == "ambiguous"
