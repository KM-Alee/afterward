"""The 14 proofs run on FakeAI through the same functions live mail will call."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engine.proofs import get_session, router, run_proofs
from app.models import ProofRun


@pytest.mark.db
def test_fourteen_proofs_pass_on_fake_ai(db_session):
    payload = run_proofs(db_session)
    failed = [item for item in payload["results"] if not item["passed"]]
    assert failed == []
    assert payload["ok"] is True
    assert payload["passed"] == 14
    stored = db_session.query(ProofRun).one()
    assert stored.results["passed"] == 14


@pytest.mark.db
def test_proof_route_returns_the_same_result(db_session):
    app = FastAPI()
    app.include_router(router)

    def override():
        yield db_session

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    response = client.post("/api/proofs/run")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["passed"] == 14
    assert [item["id"] for item in body["results"]] == list(range(1, 15))


@pytest.mark.db
def test_recorded_run_is_labelled(db_session):
    assert run_proofs(db_session)["model_output"] == "recorded model output"


@pytest.mark.db
def test_live_mode_needs_a_key_and_never_falls_back_to_recorded(db_session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        run_proofs(db_session, live=True)
