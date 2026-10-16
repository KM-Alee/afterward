"""Deterministic doubles for the revision 1 interfaces."""

from app.fakes.ai import FakeAI, fixture_key
from app.fakes.call import FakeCallSession
from app.fakes.channel import FakeChannel
from app.fakes.clock import FakeClock
from app.fakes.mailbox import FakeMailbox

__all__ = [
    "FakeAI",
    "FakeCallSession",
    "FakeChannel",
    "FakeClock",
    "FakeMailbox",
    "fixture_key",
]
