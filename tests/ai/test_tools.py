"""Family-agent tools are read-only or proposal-only, and say so when nothing backs them."""

import json

import pytest

from app.ai.client import (
    NOT_AVAILABLE,
    AgentsSDKClient,
    ToolHooks,
    tool_get_account,
    tool_get_case_status,
    tool_propose_decision,
    tool_record_dependency_answer,
)
from app.ai.schemas import DocOut, PayeeLine, StatementOut
from app.contracts import ChatMessage, ContractError


def test_without_provider_tools_say_not_available():
    hooks = ToolHooks()
    assert tool_get_case_status(hooks, "AW-1") == NOT_AVAILABLE
    assert tool_get_account(hooks, "4417") == NOT_AVAILABLE
    assert tool_propose_decision(hooks, "close it") == NOT_AVAILABLE
    assert tool_record_dependency_answer(hooks, "access", "he shared it") == NOT_AVAILABLE
    assert hooks.proposals == []


def test_read_tools_return_provider_facts():
    hooks = ToolHooks(
        case_facts=lambda ref: {"found": True, "ref": ref},
        account_facts=lambda ref: {"service": "active", "ref": ref},
    )
    assert json.loads(tool_get_case_status(hooks, "AW-1")) == {"found": True, "ref": "AW-1"}
    assert json.loads(tool_get_account(hooks, "4417"))["service"] == "active"


def test_provider_failure_is_not_leaked():
    def boom(_ref):
        raise RuntimeError("secret detail")

    hooks = ToolHooks(case_facts=boom, account_facts=boom, on_proposal=lambda *_: boom(0))
    for out in (
        tool_get_case_status(hooks, "x"),
        tool_get_account(hooks, "x"),
        tool_propose_decision(hooks, "x"),
    ):
        assert out.startswith("not available") and "secret" not in out
    assert hooks.proposals == []


def test_proposals_go_to_the_sink_and_approve_nothing():
    seen = []
    hooks = ToolHooks(on_proposal=lambda kind, payload: seen.append((kind, payload)))
    out = tool_propose_decision(hooks, "  keep   the voicemail ")
    assert "Nothing is approved" in out
    assert seen == [("decision", {"summary": "keep the voicemail"})]
    tool_record_dependency_answer(hooks, "access", "x" * 1000)
    assert seen[1][0] == "dependency" and len(seen[1][1]["statement"]) <= 400
    assert len(hooks.proposals) == 2


def test_client_exposes_case_facts_injection():
    client = AgentsSDKClient()
    assert client.case_facts is None
    client.case_facts = lambda ref: {"ref": ref}
    assert client.hooks.case_facts is not None
    assert "family_conversation" in client.agents


def _statement():
    return StatementOut(
        lines=[PayeeLine(payee="Gym", reference=None, amount="1", date="d", quote="GYM")]
    )


async def test_document_reader_can_return_a_statement():
    seen = []

    async def runner(role, messages, images):
        seen.append(role)
        return _statement()

    client = AgentsSDKClient(runner=runner)
    out = await client.structured(
        "document_reader", StatementOut, [ChatMessage(role="user", content="s")]
    )
    assert isinstance(out, StatementOut) and seen == ["document_reader"]


async def test_other_roles_cannot_return_a_statement_and_wrong_schema_rejected():
    client = AgentsSDKClient(runner=lambda *a: None)
    with pytest.raises(ContractError):
        await client.structured("reply_reader", StatementOut, [])
    with pytest.raises(ContractError):
        await client.structured("intake", DocOut, [])


def test_statement_agent_is_built_with_its_own_output_type():
    client = AgentsSDKClient()
    assert client.agents["statement_reader"].output_type is not None
