"""The chat's candidate list and the case's account rows stay one list."""

import pytest
from sqlalchemy import select

from app.discovery.agent import DiscoveryTools, apply_answer, build_suggestion, close_stale
from app.discovery.candidates import UNREFERENCED, Candidate
from app.discovery.sync import storage_ref, sync_candidates
from app.engine.demo_case import ensure_demo_case
from app.models import Account, AccountOrigin, Event, Ownership

pytestmark = pytest.mark.db


def _cand(ref: str, provider: str = "Northline Mobile", **kw) -> Candidate:
    base = {
        "account_ref": ref,
        "provider": provider,
        "service_label": f"{provider} {ref}",
        "holder_name": "",
        "origin": "household_inbox",
        "evidence": "Inbox message from billing",
        "evidence_ids": [f"inbox:{ref}"],
    }
    base.update(kw)
    return Candidate(**base)


def _account(session, case_id, ref):
    return session.scalar(
        select(Account).where(Account.case_id == case_id, Account.account_ref == ref)
    )


def test_new_chat_candidate_becomes_unconfirmed_account(db_session):
    case_id = ensure_demo_case(db_session)
    candidates = [_cand("NEW-1", "Brightline Broadband")]
    assert sync_candidates(db_session, case_id, candidates) == 1
    row = _account(db_session, case_id, "NEW-1")
    assert row.ownership is Ownership.unconfirmed
    assert row.origin is AccountOrigin.inbox
    assert row.origin_evidence.startswith("Household inbox")
    assert row.evidence_ids == ["inbox:NEW-1"]
    assert row.next_step["provider"] == "Brightline Broadband"


def test_his_inbox_origin_is_labelled_his(db_session):
    case_id = ensure_demo_case(db_session)
    sync_candidates(db_session, case_id, [_cand("NEW-2", origin="deceased_inbox")])
    assert _account(db_session, case_id, "NEW-2").origin_evidence.startswith("His inbox")


def test_existing_account_gains_evidence_not_a_duplicate(db_session):
    case_id = ensure_demo_case(db_session)
    before = len(list(db_session.scalars(select(Account).where(Account.case_id == case_id))))
    candidates = [_cand("4417", evidence_ids=["inbox:abc"])]
    assert sync_candidates(db_session, case_id, candidates) == 0
    after = len(list(db_session.scalars(select(Account).where(Account.case_id == case_id))))
    assert after == before
    assert "inbox:abc" in _account(db_session, case_id, "4417").evidence_ids


def test_chat_decision_reaches_db_with_audit_event(db_session):
    case_id = ensure_demo_case(db_session)
    candidates = [_cand("NEW-3")]
    sync_candidates(db_session, case_id, candidates)
    candidates[0].ownership = "confirmed"
    sync_candidates(db_session, case_id, candidates)
    assert _account(db_session, case_id, "NEW-3").ownership is Ownership.confirmed
    kinds = list(db_session.scalars(select(Event.kind).where(Event.case_id == case_id)))
    assert "ownership.set" in kinds


def test_web_decision_reaches_chat_and_db_wins_a_conflict(db_session):
    case_id = ensure_demo_case(db_session)
    candidates = [_cand("NEW-4")]
    sync_candidates(db_session, case_id, candidates)
    _account(db_session, case_id, "NEW-4").ownership = Ownership.not_theirs
    candidates[0].ownership = "confirmed"  # the chat disagrees
    sync_candidates(db_session, case_id, candidates)
    assert _account(db_session, case_id, "NEW-4").ownership is Ownership.not_theirs
    assert candidates[0].ownership == "removed"


def test_decision_never_moves_back_to_undecided(db_session):
    case_id = ensure_demo_case(db_session)
    candidates = [_cand("NEW-5")]
    sync_candidates(db_session, case_id, candidates)
    _account(db_session, case_id, "NEW-5").ownership = Ownership.confirmed
    sync_candidates(db_session, case_id, candidates)
    candidates[0].ownership = "unconfirmed"
    sync_candidates(db_session, case_id, candidates)
    assert _account(db_session, case_id, "NEW-5").ownership is Ownership.confirmed
    assert candidates[0].ownership == "confirmed"


def test_db_accounts_join_the_chat_list(db_session):
    case_id = ensure_demo_case(db_session)
    candidates: list[Candidate] = []
    sync_candidates(db_session, case_id, candidates)
    refs = {item.account_ref for item in candidates}
    assert {"4417", "2290", "ML-6610"} <= refs
    meridian = next(item for item in candidates if item.account_ref == "ML-6610")
    assert meridian.provider == "Meridian Life"
    assert meridian.track == "insurance_pension"


def test_unreferenced_candidates_get_separate_rows(db_session):
    case_id = ensure_demo_case(db_session)
    one = _cand(UNREFERENCED, "CloudVault", evidence_ids=["photo:1"])
    two = _cand(UNREFERENCED, "CloudVault", evidence_ids=["photo:2"])
    assert storage_ref(one) != storage_ref(two)
    assert sync_candidates(db_session, case_id, [one, two]) == 2


def test_old_button_cannot_overwrite_a_web_decision():
    tools = DiscoveryTools(candidates=[_cand("2290")])
    suggestion = build_suggestion(
        tools, kind="which_account", text="Is line 2290 his?", why="bill", target="2290"
    )
    assert not isinstance(suggestion, str)
    tools.candidates[0].ownership = "removed"  # decided on the web page
    _, reply = apply_answer(tools, suggestion.options[0].id)
    assert "already decided" in reply
    assert tools.candidates[0].ownership == "removed"


def test_close_stale_closes_only_decided_questions():
    tools = DiscoveryTools(candidates=[_cand("2290"), _cand("4417")])
    for ref in ("2290", "4417"):
        build_suggestion(tools, kind="which_account", text=f"Is {ref} his?", why="b", target=ref)
    tools.candidates[0].ownership = "confirmed"
    assert close_stale(tools) == 1
    status = {item.target: item.status for item in tools.suggestions}
    assert status == {"2290": "answered", "4417": "open"}


def test_locators_sync_both_ways_and_chat_never_marks_started(db_session):
    from app.discovery.sync import sync_locators
    from app.models import DiscoverySource

    case_id = ensure_demo_case(db_session)
    started = {"policy"}  # prepared in chat
    sync_locators(db_session, case_id, started, by="Sara")
    rows = {
        r.kind: r
        for r in db_session.scalars(
            select(DiscoverySource).where(DiscoverySource.case_id == case_id)
        )
    }
    assert rows["locator:policy"].status == "prepared"
    db_session.add(
        DiscoverySource(
            case_id=case_id,
            kind="locator:unclaimed",
            started_by="Sara",
            scope_text="x",
            status="waiting",
        )
    )
    db_session.flush()
    chat: set[str] = set()
    sync_locators(db_session, case_id, chat, by="Sara")
    assert chat == {"policy", "unclaimed"}
