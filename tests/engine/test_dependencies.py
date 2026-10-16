"""Dependency answers become conditions in code, including the access link."""

import pytest

from app.ai.schemas import DependencyOut
from app.engine.dependencies import apply_dependency, effect_for
from app.engine.plans import revise_plan
from tests.engine.support import make_account, make_case, make_owner, make_provider


def test_rule_table():
    memory = effect_for(
        DependencyOut(
            kind="memory",
            statement="His voice is on the voicemail.",
            linked_provider=None,
            linked_number=None,
            evidence_quote="His voice is on the voicemail.",
        )
    )
    access = effect_for(
        DependencyOut(
            kind="access",
            statement="The bank sends codes here.",
            linked_provider="Crescent Bank",
            linked_number="0932",
            evidence_quote="The bank sends codes here.",
        )
    )
    assert memory.conditions[0]["key"] == "voicemail_preserved"
    assert memory.conditions[0]["value"] == "true"
    assert access.conditions[0]["key"] == "number_kept"
    assert access.link_account_ref == "0932"


@pytest.mark.db
def test_access_dependency_links_the_account_and_revises_the_plan(db_session):
    case = make_case(db_session)
    owner = make_owner(db_session, case)
    provider = make_provider(db_session)
    line = make_account(db_session, case, provider, account_ref="4417")
    bank = make_account(db_session, case, provider, account_ref="0932")
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=line.id,
        action="transfer",
        conditions=[],
        documents=[],
        recipient="bereavement@northline.example",
    )
    row, revised = apply_dependency(
        db_session,
        case_id=case.id,
        account=line,
        dependency=DependencyOut(
            kind="access",
            statement="Crescent Bank sends codes to 0932.",
            linked_provider="Crescent Bank",
            linked_number="0932",
            evidence_quote="Crescent Bank sends codes to 0932.",
        ),
        source_member_id=owner.id,
        plan=plan,
    )
    assert row.linked_account_id == bank.id
    assert revised is not None
    assert revised.version == 2
    assert any(item["key"] == "number_kept" for item in revised.conditions)
    assert plan.status.value == "superseded"
