"""The showcase page and its two POST routes, over the real engine and database rows."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Account, Approval
from app.web.factory import create_surface_app
from tests.web.conftest import PASSCODE, login

pytestmark = pytest.mark.db


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


def test_showcase_is_desk_protected(client):
    assert client.get("/showcase").status_code == 401
    assert client.post("/api/showcase/next").status_code == 401
    assert client.post("/api/showcase/reset").status_code == 401


def test_page_before_reset_says_nothing_is_seeded(client):
    login(client)
    page = client.get("/showcase")
    assert page.status_code == 200
    assert "Nothing is seeded yet" in page.text
    assert "Run next step" in page.text


def test_reset_then_next_runs_real_steps(client, db_session):
    login(client)
    done = client.post("/api/showcase/reset", follow_redirects=False)
    assert done.status_code == 303
    assert db_session.scalar(select(func.count()).select_from(Account)) == 0
    first = client.post("/api/showcase/next", headers={"accept": "application/json"})
    assert first.json()["step"] == "intent"
    second = client.post("/api/showcase/next", headers={"accept": "application/json"})
    assert second.json()["step"] == "discover"
    assert db_session.scalar(select(func.count()).select_from(Account)) == 9
    page = client.get("/showcase")
    assert "Sara states it once" in page.text
    assert "Find candidate accounts" in page.text
    assert "Simulated" in page.text
    # a desk page reads the same rows the step wrote
    desk = client.get("/desk/" + str(client.app.state.surface.demo_case_id))
    assert "Northline Mobile" in desk.text
    assert db_session.scalar(select(func.count()).select_from(Approval)) == 0


def test_reset_clears_progress(client, db_session):
    login(client)
    client.post("/api/showcase/reset")
    client.post("/api/showcase/next")
    client.post("/api/showcase/reset")
    assert db_session.scalar(select(func.count()).select_from(Account)) == 0
    again = client.post("/api/showcase/next", headers={"accept": "application/json"})
    assert again.json()["step"] == "intent"
