"""Plan hashes, voiding, and compare-and-set approval."""

import pytest
from sqlalchemy import select

from app.ai.schemas import DependencyOut
from app.engine.dependencies import apply_dependency
from app.engine.errors import AlreadyDecided, DependencyRequired, StalePlan
from app.engine.plans import acceptance_allowed, approve, plan_hash, revise_plan
from app.models import Dependency
from tests.engine.support import make_account, make_case, make_owner, make_provider

CONDITIONS = [{"key": "number_kept", "type": "bool", "value": "true"}]
DOCUMENTS = [{"type": "death_certificate", "form": "photo"}]


@pytest.mark.db
def test_hash_covers_action_conditions_documents_and_recipient(db_session):
    case = make_case(db_session)
    account = make_account(db_session, case, make_provider(db_session))
    first = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="close",
        conditions=CONDITIONS,
        documents=DOCUMENTS,
        recipient="bereavement@northline.example",
    )
    assert first.version == 1
    assert first.hash == plan_hash("close", CONDITIONS, DOCUMENTS, "bereavement@northline.example")
    same = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="close",
        conditions=list(reversed(CONDITIONS)),
        documents=DOCUMENTS,
        recipient="bereavement@northline.example",
        fallback="different fallback",
    )
    assert same.id == first.id
    changed = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="close",
        conditions=CONDITIONS,
        documents=DOCUMENTS,
        recipient="other@northline.example",
    )
    assert changed.version == 2
    assert changed.hash != first.hash
    assert first.status.value == "superseded"


@pytest.mark.db
def test_approve_is_compare_and_set_and_voids_when_the_hash_changes(db_session):
    case = make_case(db_session)
    owner = make_owner(db_session, case)
    provider = make_provider(db_session)
    account = make_account(db_session, case, provider)
    bank = make_account(db_session, case, provider, account_ref="0932")
    apply_dependency(
        db_session,
        case_id=case.id,
        account=account,
        dependency=DependencyOut(
            kind="access",
            statement="Crescent Bank sends codes to this number.",
            linked_provider="Crescent Bank",
            linked_number="0932",
            evidence_quote="Crescent Bank sends codes to this number.",
        ),
        source_member_id=owner.id,
        plan=None,
    )
    row = db_session.scalar(select(Dependency).where(Dependency.account_id == account.id))
    assert row is not None
    assert row.linked_account_id == bank.id
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="transfer",
        conditions=CONDITIONS,
        documents=DOCUMENTS,
        recipient="bereavement@northline.example",
    )
    with pytest.raises(StalePlan) as stale:
        approve(
            db_session,
            plan_id=plan.id,
            version=plan.version,
            plan_hash_value="0" * 64,
            member_id=owner.id,
        )
    assert stale.value.status_code == 409
    approval = approve(
        db_session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=owner.id,
    )
    assert acceptance_allowed(db_session, approval.id)
    with pytest.raises(AlreadyDecided) as decided:
        approve(
            db_session,
            plan_id=plan.id,
            version=plan.version,
            plan_hash_value=plan.hash,
            member_id=owner.id,
        )
    assert decided.value.status_code == 409
    revised = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="transfer",
        conditions=CONDITIONS + [{"key": "contract_months", "type": "max_int", "value": "24"}],
        documents=DOCUMENTS,
        recipient="bereavement@northline.example",
    )
    db_session.refresh(approval)
    assert approval.status.value == "void"
    assert acceptance_allowed(db_session, approval.id) is False
    with pytest.raises(StalePlan):
        approve(
            db_session,
            plan_id=plan.id,
            version=plan.version,
            plan_hash_value=plan.hash,
            member_id=owner.id,
        )
    assert revised.version == 2


@pytest.mark.db
def test_close_without_a_dependency_is_refused(db_session):
    case = make_case(db_session)
    owner = make_owner(db_session, case)
    account = make_account(db_session, case, make_provider(db_session))
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="close",
        conditions=[],
        documents=[],
        recipient="bereavement@northline.example",
    )
    with pytest.raises(DependencyRequired):
        approve(
            db_session,
            plan_id=plan.id,
            version=plan.version,
            plan_hash_value=plan.hash,
            member_id=owner.id,
        )
