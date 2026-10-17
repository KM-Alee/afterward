"""The desk, family page and onboarding read database rows; the demo fallback says so."""

import types
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Account, Decision, Event, Job, MailConnection, Ownership
from app.web.onboarding import suggestions
from app.web.state import DEMO_CASE_ID
from tests.web.conftest import login, token_for


def _demo_accounts(session):
    return {a.account_ref: a for a in session.scalars(select(Account))}


@pytest.mark.db
def test_desk_is_projected_from_rows_and_names_the_real_origin(db_client):
    login(db_client)
    page = db_client.get(f"/desk/{DEMO_CASE_ID}")
    assert page.status_code == 200
    assert "Live from the database" in page.text
    assert "Demo data (not from the database)" not in page.text
    assert "Yusuf Malik" in page.text
    assert "Northline Mobile" in page.text
    assert "Found in: Forward" in page.text
    assert "Found in: Photo" in page.text
    assert "Unconfirmed" in page.text
    # the FitLife follow-up is a real queued job, shown as scheduled
    assert "Scheduled" in page.text
    assert "Follow-up" in page.text


def test_fallback_without_a_database_is_labelled(client):
    login(client)
    page = client.get(f"/desk/{DEMO_CASE_ID}")
    assert "Demo data (not from the database)" in page.text
    assert "Live from the database" not in page.text


@pytest.mark.db
def test_clock_jump_moves_the_case_clock_and_sends_nothing_directly(db_client, db_session):
    login(db_client)
    surface = db_client.app.state.surface
    # the seed ran "long ago": inside one test transaction now() is the start of the transaction
    seeded = db_session.scalar(select(Job).where(Job.kind == "followup"))
    seeded.run_at_case_time = seeded.run_at_case_time - timedelta(hours=1)
    db_session.flush()
    moved = db_client.post(
        f"/api/cases/{DEMO_CASE_ID}/clock", data={"advance_days": "14"}, follow_redirects=False
    )
    assert moved.status_code == 303
    case = db_session.scalars(select(Account)).first()
    from app.models import Case

    row = db_session.scalar(select(Case).where(Case.ref == "AW-1042"))
    db_session.refresh(row)
    assert row.clock_offset_s == 14 * 86400
    assert surface.mailbox.sent == []
    assert case is not None
    kinds = {job.kind for job in db_session.scalars(select(Job).where(Job.case_id == row.id))}
    assert "followup" in kinds
    followup = db_session.scalar(select(Job).where(Job.kind == "followup"))
    # gentle autopilot: the runner ran the job, and instead of sending it asked the family
    decisions = db_session.scalars(select(Decision).where(Decision.case_id == row.id)).all()
    assert len(decisions) == 1
    assert followup.status.value == "pending"
    audit = db_session.scalars(select(Event).where(Event.kind == "clock.advanced")).all()
    assert len(audit) == 1
    rejected = db_client.post(f"/api/cases/{DEMO_CASE_ID}/clock", data={"advance_days": "3"})
    assert rejected.status_code == 422


@pytest.mark.db
def test_reset_restores_the_rows_and_keeps_a_connected_mailbox(db_client, db_session):
    login(db_client)
    from app.models import Case

    case = db_session.scalar(select(Case).where(Case.ref == "AW-1042"))
    db_session.add(
        MailConnection(
            case_id=case.id,
            owner_label="Sara",
            account_of="household",
            address="family@example.test",
            stated_authority="",
        )
    )
    _demo_accounts(db_session)["2290"].ownership = Ownership.confirmed
    db_session.flush()
    reset = db_client.post(f"/api/cases/{DEMO_CASE_ID}/reset", follow_redirects=False)
    assert reset.status_code == 303
    again = db_session.scalar(select(Case).where(Case.ref == "AW-1042"))
    accounts = {
        a.account_ref: a
        for a in db_session.scalars(select(Account).where(Account.case_id == again.id))
    }
    assert accounts["2290"].ownership is Ownership.unconfirmed
    kept = db_session.scalars(
        select(MailConnection).where(MailConnection.case_id == again.id)
    ).all()
    assert [c.address for c in kept] == ["family@example.test"]


@pytest.mark.db
def test_reset_refuses_a_non_demo_case(db_client, db_session):
    login(db_client)
    from app.models import Case

    case = db_session.scalar(select(Case).where(Case.ref == "AW-1042"))
    case.clock_offset_s = 0
    case.is_demo = False
    db_session.flush()
    reset = db_client.post(f"/api/cases/{DEMO_CASE_ID}/reset")
    assert reset.status_code == 403


@pytest.mark.db
def test_onboarding_page_renders_sources_candidates_and_coverage(db_client):
    surface = db_client.app.state.surface
    token = token_for(surface.family_tokens, DEMO_CASE_ID)
    page = db_client.get(f"/family/{token}/onboarding")
    assert page.status_code == 200
    text = page.text
    assert "Where should we look, Sara?" in text
    assert "Connect Gmail" in text
    assert "Your authority" in text
    assert "Yes, his" in text and "Not his" in text and "Shared or not sure" in text
    assert "Searches you can run" in text
    assert "Not searched, by design" in text
    assert "Prepared for you, done by you" in text
    assert "found everything" in text  # only inside "we never say we have found everything"
    assert "access_token" not in text and "refresh" not in text.casefold()
    assert db_client.get("/family/not-a-token/onboarding").status_code == 404
    assert db_client.get("/family/onboarding").status_code == 401
    login(db_client)
    entry = db_client.get("/family/onboarding", follow_redirects=False)
    assert entry.status_code == 303 and entry.headers["location"].endswith("/onboarding")


@pytest.mark.db
def test_ownership_buttons_use_the_set_ownership_path(db_client, db_session):
    surface = db_client.app.state.surface
    token = token_for(surface.family_tokens, DEMO_CASE_ID)
    accounts = _demo_accounts(db_session)
    url = f"/family/{token}/onboarding/ownership"
    yes = db_client.post(
        url, data={"account_id": str(accounts["2290"].id), "choice": "his"}, follow_redirects=False
    )
    assert yes.status_code == 303
    assert accounts["2290"].ownership is Ownership.confirmed
    no = db_client.post(url, data={"account_id": str(accounts["ML-6610"].id), "choice": "not_his"})
    assert no.status_code in (200, 303)
    assert accounts["ML-6610"].ownership is Ownership.not_theirs
    unsure = db_client.post(
        url, data={"account_id": str(accounts["0932"].id), "choice": "not_sure"}
    )
    assert unsure.status_code in (200, 303)
    assert accounts["0932"].ownership is Ownership.unconfirmed
    assert accounts["0932"].next_step["flag"] == "needs_check"
    audit = db_session.scalars(select(Event).where(Event.kind == "ownership.set")).all()
    assert len(audit) == 3


@pytest.mark.db
def test_ownership_deny_paths(db_client, db_session):
    surface = db_client.app.state.surface
    token = token_for(surface.family_tokens, DEMO_CASE_ID)
    accounts = _demo_accounts(db_session)
    url = f"/family/{token}/onboarding/ownership"
    ident = str(accounts["2290"].id)
    assert db_client.post(url, data={"account_id": ident, "choice": "admin"}).status_code == 422
    assert db_client.post(url, data={"account_id": "nope", "choice": "his"}).status_code == 422
    assert accounts["2290"].ownership is Ownership.unconfirmed
    done = str(accounts["4417"].id)  # already confirmed by the seed
    assert db_client.post(url, data={"account_id": done, "choice": "not_his"}).status_code == 409
    assert accounts["4417"].ownership is Ownership.confirmed
    bad = db_client.post(
        "/family/not-a-token/onboarding/ownership", data={"account_id": ident, "choice": "his"}
    )
    assert bad.status_code == 404


@pytest.mark.db
def test_tell_us_adds_an_unconfirmed_candidate(db_client, db_session):
    surface = db_client.app.state.surface
    token = token_for(surface.family_tokens, DEMO_CASE_ID)
    told = db_client.post(f"/family/{token}/onboarding/tell", data={"text": "a gym membership"})
    assert told.status_code == 200
    assert "a gym membership" in told.text
    row = _demo_accounts(db_session)["told-1"]
    assert row.ownership is Ownership.unconfirmed
    empty = db_client.post(f"/family/{token}/onboarding/tell", data={"text": "  "})
    assert empty.status_code == 422


@pytest.mark.db
def test_locator_is_prepared_before_it_can_be_started(db_client):
    surface = db_client.app.state.surface
    token = token_for(surface.family_tokens, DEMO_CASE_ID)
    url = f"/family/{token}/onboarding/locator"
    early = db_client.post(url, data={"locator": "policy", "step": "started"})
    assert early.status_code == 409
    assert db_client.post(url, data={"locator": "policy", "step": "prepare"}).status_code == 200
    started = db_client.post(url, data={"locator": "policy", "step": "started"})
    assert "Started by Sara Malik, waiting" in started.text
    assert "Started, waiting" in started.text
    assert db_client.post(url, data={"locator": "nope", "step": "prepare"}).status_code == 422


def _fake_connect(monkeypatch, *, finish=None):
    """Replace the two network-facing connect functions on the real module."""
    from app.integrations import connect as connect_mod

    calls: list[dict] = []

    def start_connect(settings, *, case_id, account_of, stated_authority, owner_label):
        calls.append(
            {"account_of": account_of, "authority": stated_authority, "owner": owner_label}
        )
        return "https://accounts.example/auth?state=abc"

    def finish_connect(settings, session, *, state, code):
        if finish is not None:
            return finish(state)
        raise connect_mod.ConnectError("bad state")

    monkeypatch.setattr(connect_mod, "start_connect", start_connect)
    monkeypatch.setattr(connect_mod, "finish_connect", finish_connect)
    return calls


def _with_settings(client):
    from app.config import Settings

    client.app.state.settings = Settings()


@pytest.mark.db
def test_connecting_his_mailbox_needs_a_stated_authority(db_client, monkeypatch):
    calls = _fake_connect(monkeypatch)
    _with_settings(db_client)
    token = token_for(db_client.app.state.surface.family_tokens, DEMO_CASE_ID)
    blank = db_client.post(
        "/connect/gmail/start",
        data={"token": token, "account_of": "deceased", "stated_authority": "   "},
        follow_redirects=False,
    )
    assert blank.status_code == 400
    assert "right to open his mailbox" in blank.text
    assert calls == []
    odd = db_client.post("/connect/gmail/start", data={"token": token, "account_of": "bank"})
    assert odd.status_code == 400
    stranger = db_client.post(
        "/connect/gmail/start", data={"token": "nope", "account_of": "household"}
    )
    assert stranger.status_code == 404


@pytest.mark.db
def test_connect_start_redirects_to_the_sign_in_url(db_client, monkeypatch):
    calls = _fake_connect(monkeypatch)
    _with_settings(db_client)
    token = token_for(db_client.app.state.surface.family_tokens, DEMO_CASE_ID)
    sent = db_client.post(
        "/connect/gmail/start",
        data={
            "token": token,
            "account_of": "deceased",
            "stated_authority": "the provider released an export to me",
        },
        follow_redirects=False,
    )
    assert sent.status_code == 303
    assert sent.headers["location"] == "https://accounts.example/auth?state=abc"
    assert calls == [
        {
            "account_of": "deceased",
            "authority": "the provider released an export to me",
            "owner": "Sara Malik",
        }
    ]


@pytest.mark.db
def test_callback_with_a_bad_state_is_refused(db_client, monkeypatch):
    _fake_connect(monkeypatch)
    _with_settings(db_client)
    bad = db_client.get("/connect/gmail/callback?state=forged&code=abc", follow_redirects=False)
    assert bad.status_code == 400
    assert db_client.get("/connect/gmail/callback", follow_redirects=False).status_code == 400


@pytest.mark.db
def test_callback_success_returns_to_the_page_without_showing_tokens(db_client, monkeypatch):
    _fake_connect(monkeypatch, finish=lambda state: types.SimpleNamespace(case_id=None))
    _with_settings(db_client)
    done = db_client.get("/connect/gmail/callback?state=ok&code=abc", follow_redirects=True)
    assert done.status_code == 200
    assert "Mailbox connected" in done.text
    assert "abc" not in done.text


def test_suggestions_never_claim_the_search_is_finished():
    rows = [
        {
            "id": "1",
            "provider": "Northline Mobile",
            "label": "Line 2290",
            "state": "proposed",
            "sources": "Photo",
            "track": "ordinary",
        },
        {
            "id": "2",
            "provider": "Northline Mobile",
            "label": "Line 4417",
            "state": "confirmed",
            "sources": "Forward",
            "track": "ordinary",
        },
        {
            "id": "3",
            "provider": "Crescent Bank",
            "label": "Account",
            "state": "proposed",
            "sources": "Forward",
            "track": "financial",
        },
    ]
    found = suggestions(rows)
    assert found
    for item in found:
        low = f" {item['text'].casefold()} "
        assert not any(word in low for word in ("all ", "every", "complete", "nothing else"))
        assert len(item["options"]) <= 3


@pytest.mark.db
def test_call_room_gets_the_request_from_the_approved_plan(db_client):
    from app.web.plan_text import request_text_for

    factory = db_client.app.state.session_factory
    text = request_text_for(factory, DEMO_CASE_ID, "FL-5531")
    assert text is not None and "Membership FL-5531" in text
    assert request_text_for(factory, DEMO_CASE_ID, "4417") is None  # no approved plan
    surface = db_client.app.state.surface
    room = surface.calls[token_for(surface.call_tokens, DEMO_CASE_ID)]
    assert room.request_provider is not None
    assert room.request_provider() is None


def test_proof_report_says_whether_the_model_was_recorded_or_live():
    from app.web.proofs import PROOF_CASES, _page_report

    results = [{"passed": True, "records": {}, "latency_ms": 0} for _ in PROOF_CASES]
    recorded = _page_report({"passed": 14, "failed": 0, "results": results})
    assert recorded["model_output"] == "recorded model output"
    live = _page_report(
        {"passed": 14, "failed": 0, "results": results, "model_output": "live model output"}
    )
    assert live["model_output"] == "live model output"
    unknown = _page_report(
        {"passed": 14, "failed": 0, "results": results, "model_output": "trust me"}
    )
    assert unknown["model_output"] == "recorded model output"
