"""Showcase tests: the steps run against real Postgres rows with the simulated outside world."""

from contextlib import contextmanager

import pytest

from app.demo.showcase import ShowcaseEnv, reset_showcase, run_step
from app.engine import jobs as jobs_module


@pytest.fixture(autouse=True)
def wall_clock_lease(monkeypatch):
    """Inside the rolled-back test transaction now() is frozen; the lease query needs real time."""
    monkeypatch.setattr(
        jobs_module, "_LEASE_SQL", jobs_module._LEASE_SQL.replace("now()", "clock_timestamp()")
    )


@pytest.fixture
def factory(db_session):
    @contextmanager
    def make():
        yield db_session

    return make


@pytest.fixture
def env():
    return ShowcaseEnv()


@pytest.fixture
def started(db_session):
    """The pre-onboarding start state and its case id."""
    return reset_showcase(db_session)


@pytest.fixture
def play(factory, env, started):
    """Run the named steps in order and return their results by id."""

    async def go(*step_ids: str):
        results = {}
        for step_id in step_ids:
            results[step_id] = await run_step(factory, env, step_id)
        return results

    return go
