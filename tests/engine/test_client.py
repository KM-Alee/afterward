"""The Agents SDK client stays offline unless a runner is injected."""

import asyncio

import pytest
from pydantic import BaseModel

from app.ai.client import (
    ACCURATE_MODEL,
    CARE_RESPONSE,
    CONSEQUENTIAL_TOOLS,
    FAST_MODEL,
    UPGRADE_MODEL,
    AgentsSDKClient,
    output_missing_quote,
    screen_crisis,
    tool_grants_permission,
)
from app.ai.schemas import DocOut, IntakeOut, ReplyOut
from app.contracts import ChatMessage, ContractError, ImageInput
from app.engine.errors import AIUnavailable, CrisisPaused


def _reply() -> ReplyOut:
    return ReplyOut.model_validate(
        {
            "commitments": [
                {
                    "account_hint": "4417",
                    "action": "close",
                    "status": "acknowledged",
                    "negated": False,
                    "conditions_or_requirements": [],
                    "facts": [],
                    "scope": "this_service",
                    "effective_date": None,
                    "evidence_quote": "We received your request",
                    "interpretation": "clear",
                }
            ],
            "asks_for_documents": [],
            "is_marketing_to_deceased": False,
        }
    )


def test_models_guardrails_and_approvals_do_not_open_a_socket():
    client = AgentsSDKClient()
    assert client.model_for("reply_reader") == ACCURATE_MODEL
    assert client.model_for("intake") == FAST_MODEL
    assert client.upgrade_model() == UPGRADE_MODEL
    assert client.agents["reply_reader"].model == ACCURATE_MODEL
    assert client.agents["document_reader"].model == FAST_MODEL
    assert client.agents["reply_reader"].output_type is ReplyOut
    assert client.agents["intake"].output_type is IntakeOut
    names = {tool.name: tool for tool in client.agents["family_conversation"].tools}
    assert names["propose_decision"].needs_approval is True
    assert names["record_dependency_answer"].needs_approval is True
    assert names["get_case_status"].needs_approval is False
    assert set(names) >= CONSEQUENTIAL_TOOLS
    assert tool_grants_permission("propose_decision") is False
    assert client.agents["family_conversation"].handoffs[0].name == "dependency"
    guard = client.agents["intake"].input_guardrails[0].guardrail_function
    tripped = guard(None, None, "I want to die")
    assert tripped.tripwire_triggered is True
    assert "findahelpline.com" in CARE_RESPONSE
    assert screen_crisis("please close the gym") is False
    quote_guard = client.agents["reply_reader"].output_guardrails[0].guardrail_function
    empty = _reply().model_copy(
        update={"commitments": [_reply().commitments[0].model_copy(update={"evidence_quote": ""})]}
    )
    assert quote_guard(None, None, empty).tripwire_triggered is True
    assert output_missing_quote(_reply()) is False


@pytest.mark.asyncio
async def test_structured_retries_and_refuses_a_live_call_without_a_key():
    calls = {"n": 0}

    async def flaky(role, messages, images):
        del role, messages, images
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError
        return _reply()

    client = AgentsSDKClient(runner=flaky, max_retries=2, retry_sleep_s=0, timeout_s=1)
    result = await client.structured(
        "reply_reader",
        ReplyOut,
        [ChatMessage(role="user", content="We received your request")],
    )
    assert isinstance(result, ReplyOut)
    assert calls["n"] == 2
    with pytest.raises(ContractError):
        await client.structured("reply_reader", IntakeOut, [ChatMessage(role="user", content="no")])
    with pytest.raises(CrisisPaused):
        await AgentsSDKClient(runner=flaky).structured(
            "intake",
            IntakeOut,
            [ChatMessage(role="user", content="I want to die")],
        )
    bare = AgentsSDKClient(max_retries=0, timeout_s=1)
    with pytest.raises(AIUnavailable):
        await bare.structured("reply_reader", ReplyOut, [ChatMessage(role="user", content="hello")])
    with pytest.raises(AIUnavailable):
        await anext(bare.speak_stream("approved sentence"))
    with pytest.raises(AIUnavailable):
        await bare.transcribe(b"audio", mime="audio/webm")


@pytest.mark.asyncio
async def test_phone_photo_is_forced_and_timeouts_retry():
    async def slow(role, messages, images):
        del role, messages, images
        await asyncio.sleep(1)
        return _reply()

    client = AgentsSDKClient(runner=slow, max_retries=0, timeout_s=0.01)
    with pytest.raises(AIUnavailable):
        await client.structured(
            "reply_reader",
            ReplyOut,
            [ChatMessage(role="user", content="late")],
        )

    async def vision(role, messages, images):
        del role, messages, images
        return DocOut(
            doc_type="death_certificate",
            form="certified_copy_held",
            name=None,
            date_of_death=None,
            certificate_number=None,
            provider=None,
            account_reference=None,
            amounts=[],
            billing_period=None,
            quotes=["Yusuf Malik"],
            confidence="low",
        )

    seen = await AgentsSDKClient(runner=vision, max_retries=0).structured(
        "document_reader",
        DocOut,
        [ChatMessage(role="user", content="photo")],
        images=[ImageInput(data=b"png", mime="image/png")],
    )
    assert seen.form == "photo"
    assert isinstance(seen, BaseModel)


@pytest.mark.db
def test_sqlalchemy_session_constructs_without_an_openai_socket(db_engine):
    from sqlalchemy.ext.asyncio import create_async_engine

    url = db_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(url)
    client = AgentsSDKClient(session_engine=engine)
    memory = client.conversation_session("member-sara")
    assert memory.session_id == "member-sara"
    engine.sync_engine.dispose()
