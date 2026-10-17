"""The guided tour: its config, state and the three 'you play the role' moments."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.schemas import (
    CommitmentOut,
    DependencyOut,
    Fact,
    HouseholdMemberOut,
    IntakeOut,
    QuotedStr,
    ReplyOut,
)
from app.ai.verify import strip_quoted_history
from app.conversation.dependency import dependency_messages
from app.conversation.intake import intake_messages
from app.demo import showcase_data as data
from app.engine.pipeline import extraction_messages
from app.fakes import FakeAI
from app.models import Case, Plan
from app.web.factory import create_surface_app
from tests.web.conftest import PASSCODE, login

pytestmark = pytest.mark.db

JSON = {"accept": "application/json"}
SARA_SAYS = (
    "My dad Yusuf Malik died on 3 March 2026. I'm Sara, his daughter. "
    "Keep Mum's phone and Dad's voicemail, stop the bills nobody needs."
)
AMINA_SAYS = "That's my number and his voice is on the voicemail."
NORTHLINE_SAYS = "Done — line moved to Mrs Malik on a new 24-month plan, voicemail will be reset."


@pytest.fixture
def client(db_session, monkeypatch):
    from app.engine import jobs as jobs_module

    monkeypatch.setattr(
        jobs_module, "_LEASE_SQL", jobs_module._LEASE_SQL.replace("now()", "clock_timestamp()")
    )
    app = create_surface_app(demo_passcode=PASSCODE)

    @contextmanager
    def factory():
        yield db_session

    app.state.session_factory = factory
    with TestClient(app) as test_client:
        yield test_client


def _intake(text: str) -> IntakeOut:
    return IntakeOut(
        deceased_name=QuotedStr(value="Yusuf Malik", quote="Yusuf Malik"),
        date_of_death=QuotedStr(value="2026-03-03", quote="3 March 2026"),
        speaker_name=QuotedStr(value="Sara", quote="I'm Sara"),
        stated_role=QuotedStr(value="his daughter", quote="his daughter"),
        household_members=[
            HouseholdMemberOut(name=None, relationship="made up", quote="never said this")
        ],
        intent_keep=[
            QuotedStr(value="Mum's phone", quote="Keep Mum's phone"),
            QuotedStr(value="a house", quote="keep the house"),
        ],
        intent_stop=[QuotedStr(value="Unneeded bills", quote="stop the bills nobody needs")],
        intent_protect=[],
        missing_fields=[],
    )


def _live_ai_for_intake() -> FakeAI:
    ai = FakeAI()
    ai.register_structured("intake", IntakeOut, intake_messages(SARA_SAYS), _intake(SARA_SAYS))
    return ai


def test_tour_and_live_routes_need_the_desk_passcode(client):
    for path in (
        "/api/showcase/live/intake",
        "/api/showcase/live/dependency",
        "/api/showcase/live/reply",
        "/api/showcase/run-to",
        "/api/showcase/tour/state",
    ):
        assert client.post(path, json={"text": "x"}).status_code == 401
    assert client.get("/api/showcase/tour").status_code == 401


def test_tour_config_lists_every_stop_with_a_url(client):
    login(client)
    body = client.get("/api/showcase/tour").json()
    kinds = {stop["live"] for stop in body["stops"] if stop.get("live")}
    assert kinds == {"intake", "dependency", "reply"}
    assert all(stop["url"].startswith("/") for stop in body["stops"])
    assert any(stop["page"] == "call" and "/call/" in stop["url"] for stop in body["stops"])
    assert body["model"] == "Recorded model output"


def test_tour_position_is_saved_on_the_server(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    saved = client.post("/api/showcase/tour/state", json={"active": True, "index": 4}).json()
    assert saved["state"]["index"] == 4
    again = client.get("/api/showcase/tour").json()
    assert again["state"]["active"] is True and again["state"]["index"] == 4
    client.post("/api/showcase/tour/state", json={"index": 999})
    assert client.get("/api/showcase/tour").json()["state"]["index"] == len(data.TOUR) - 1


@pytest.mark.parametrize("kind", ["intake", "dependency", "reply"])
def test_empty_input_is_refused(client, kind):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    assert client.post(f"/api/showcase/live/{kind}", json={"text": "   "}).status_code == 422
    assert client.post(f"/api/showcase/live/{kind}", json={}).status_code == 422


def test_without_a_model_the_recorded_reading_is_labelled(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    res = client.post("/api/showcase/live/intake", json={"text": SARA_SAYS})
    body = res.json()
    assert res.status_code == 200 and body["source"] == "Recorded model output"
    assert "recorded" in body["note"].lower()
    assert body["text"] == data.SARA_TRANSCRIPT  # the typed words were not what was read
    assert body["card"]["dropped"] == 2


def test_live_intake_keeps_only_quoted_facts_and_labels_the_model(client, db_session):
    client.app.state.showcase_ai = _live_ai_for_intake()
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    body = client.post("/api/showcase/live/intake", json={"text": SARA_SAYS}).json()
    assert body["source"] == "Live model"
    card = body["card"]
    assert [q["value"] for q in card["keep"]] == ["Mum's phone"]  # "a house" had no quote
    assert card["dropped"] == 2  # the invented household member and the invented keep
    case = db_session.scalar(select(Case).where(Case.ref == data.CASE_REF))
    assert case.date_of_death.isoformat() == "2026-03-03"
    assert case.intent["keep"] == ["Mum's phone"]
    # the tour remembers the card across page loads
    saved = client.get("/api/showcase/tour").json()["state"]["live"]["intake"]
    assert saved["source"] == "Live model"


def test_a_failing_live_model_falls_back_and_says_so(client):
    client.app.state.showcase_ai = FakeAI()  # nothing registered: every call fails
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    body = client.post("/api/showcase/live/intake", json={"text": SARA_SAYS}).json()
    assert body["source"] == "Recorded model output"
    assert "did not answer" in body["note"]


def _prepare_for_dependency(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    assert client.post("/api/showcase/run-to", json={"step": "confirm"}).json()["ok"]


def test_live_dependency_rewrites_the_plan_from_the_words_typed(client, db_session):
    ai = FakeAI()
    ai.register_structured(
        "dependency",
        DependencyOut,
        dependency_messages(AMINA_SAYS),
        DependencyOut(
            kind="memory",
            statement="His voice is on the voicemail.",
            linked_provider=None,
            linked_number=None,
            evidence_quote="his voice is on the voicemail",
        ),
    )
    client.app.state.showcase_ai = ai
    _prepare_for_dependency(client)
    body = client.post("/api/showcase/live/dependency", json={"text": AMINA_SAYS}).json()
    assert body["source"] == "Live model"
    assert body["card"]["after"]["conditions"] == ["voicemail_preserved"]
    plans = db_session.scalars(select(Plan).where(Plan.version == 2)).all()
    assert any([c["key"] for c in p.conditions] == ["voicemail_preserved"] for p in plans)


def test_live_dependency_with_a_quote_not_in_the_words_is_refused(client):
    ai = FakeAI()
    ai.register_structured(
        "dependency",
        DependencyOut,
        dependency_messages(AMINA_SAYS),
        DependencyOut(
            kind="access",
            statement="Invented.",
            linked_provider=None,
            linked_number=None,
            evidence_quote="she said something else entirely",
        ),
    )
    client.app.state.showcase_ai = ai
    _prepare_for_dependency(client)
    res = client.post("/api/showcase/live/dependency", json={"text": AMINA_SAYS})
    assert res.status_code == 422


def test_live_dependency_before_the_earlier_steps_runs_them_first(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    body = client.post("/api/showcase/live/dependency", json={"text": AMINA_SAYS}).json()
    assert body["source"] == "Recorded model output"
    assert body["card"]["after"]["conditions"] == ["number_kept", "voicemail_preserved"]


def _northline_reading() -> ReplyOut:
    def fact(key, value, quote):
        return Fact.model_validate({"key": key, "value": value, "evidence_quote": quote})

    return ReplyOut(
        commitments=[
            CommitmentOut.model_validate(
                {
                    "account_hint": "4417",
                    "action": "transfer",
                    "status": "completed",
                    "negated": False,
                    "conditions_or_requirements": [],
                    "facts": [
                        fact("voicemail_preserved", "false", "voicemail will be reset"),
                        fact("contract_months", "24", "24-month plan"),
                    ],
                    "scope": "this_service",
                    "effective_date": None,
                    "interpretation": "clear",
                    "evidence_quote": "line moved to Mrs Malik",
                }
            )
        ],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )


def test_live_reply_is_judged_against_the_approved_plan(client):
    ai = FakeAI()
    ai.register_structured(
        "reply_reader",
        ReplyOut,
        extraction_messages(strip_quoted_history(NORTHLINE_SAYS)),
        _northline_reading(),
    )
    client.app.state.showcase_ai = ai
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    assert client.post("/api/showcase/run-to", json={"step": "send"}).json()["ok"]
    body = client.post("/api/showcase/live/reply", json={"text": NORTHLINE_SAYS}).json()
    assert body["source"] == "Live model"
    states = {row["key"]: row["state"] for row in body["card"]["rows"]}
    assert states["voicemail_preserved"] == "Broken"
    assert states["number_kept"] == "Not stated"
    assert states["new_contract"] == "Not approved"
    assert body["card"]["verdict"].startswith("Not done")
    voicemail = next(r for r in body["card"]["rows"] if r["key"] == "voicemail_preserved")
    assert voicemail["quote"] == "voicemail will be reset"
    # a second try is refused rather than duplicating the reply
    again = client.post("/api/showcase/live/reply", json={"text": NORTHLINE_SAYS})
    assert again.status_code == 422


def test_recorded_reply_still_catches_the_wrong_outcome(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    client.post("/api/showcase/run-to", json={"step": "send"})
    body = client.post("/api/showcase/live/reply", json={"text": NORTHLINE_SAYS}).json()
    assert body["source"] == "Recorded model output"
    assert body["card"]["kind"] == "needs_decision"


def test_run_to_runs_the_prerequisites_and_refuses_unknown_steps(client):
    login(client)
    client.post("/api/showcase/reset", headers=JSON)
    done = client.post("/api/showcase/run-to", json={"step": "discover"}).json()
    assert done["step"] == "discover"
    assert client.post("/api/showcase/run-to", json={"step": "nope"}).status_code == 409
    assert client.post("/api/showcase/run-to", json={}).status_code == 422
