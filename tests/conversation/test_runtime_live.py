"""Runtime wiring: dedupe and snapshots through the real functions, queued sends in after_turn."""

from types import SimpleNamespace

import pytest

import app.runtime as runtime
from app.conversation.demo_malik import (
    ALLOWED_RECIPIENTS,
    NORTHLINE,
    PROVIDERS,
    run_malik_script,
)
from app.conversation.session import Conversation
from app.fakes import FakeAI, FakeChannel


class _Proxy:
    """Stands in for Session(engine): shares the test transaction, never closes it."""

    def __init__(self, session):
        self.s = session

    def __enter__(self):
        return self

    def __getattr__(self, name):
        return getattr(self.s, name)

    def __exit__(self, *exc):
        return False


@pytest.mark.db
def test_update_dedupe_and_snapshot_use_the_database(db_session, monkeypatch):
    monkeypatch.setattr(runtime, "_db_session", lambda _s: _Proxy(db_session))
    assert runtime._claim_update(object(), 700) is True
    assert runtime._claim_update(object(), 700) is False  # retry is not processed again


def test_without_a_database_the_claim_is_unknown(monkeypatch):
    monkeypatch.setattr(runtime, "_db_session", lambda _s: None)
    assert runtime._claim_update(object(), 1) is None


async def _approved():
    result = await run_malik_script(FakeAI(), FakeChannel())
    conv = result.conversation
    replies = await conv.handle_button("1001", "approve_plan")
    return conv, replies


def _app():
    return SimpleNamespace(state=SimpleNamespace(surface=None, settings=None))


@pytest.mark.asyncio
async def test_after_turn_reports_a_queued_send_and_does_not_send_directly(monkeypatch):
    conv, replies = await _approved()
    monkeypatch.setattr(runtime, "_queue_send", lambda *_a: True)
    out = await runtime.after_turn(_app(), conv, "1001", replies)
    assert out[-1].kind == "request_queued"
    assert "once" in out[-1].text


@pytest.mark.asyncio
async def test_after_turn_says_nothing_was_sent_when_the_plan_cannot_be_bound(monkeypatch):
    conv, replies = await _approved()
    monkeypatch.setattr(runtime, "_queue_send", lambda *_a: False)
    out = await runtime.after_turn(_app(), conv, "1001", replies)
    assert out[-1].kind == "request_not_queued"
    assert "nothing was queued or sent" in out[-1].text


@pytest.mark.asyncio
async def test_after_turn_without_an_approval_card_queues_nothing(monkeypatch):
    conv = Conversation(
        FakeAI(), providers=PROVIDERS, allowed_recipients=ALLOWED_RECIPIENTS, line=NORTHLINE
    )
    called = []
    monkeypatch.setattr(runtime, "_queue_send", lambda *_a: called.append(1) or True)
    from app.conversation.session import Outbound

    out = await runtime.after_turn(
        _app(), conv, "1001", [Outbound("1001", "x", kind="approval_recorded")]
    )
    assert called == [] and [r.kind for r in out] == ["approval_recorded"]
