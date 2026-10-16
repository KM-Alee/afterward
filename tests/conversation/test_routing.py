"""Commands, crisis, off-topic declines, decisions and the finish question."""

from datetime import UTC, date, datetime

import pytest

from app.conversation.demo_malik import ALLOWED_RECIPIENTS, NORTHLINE, PROVIDERS
from app.conversation.session import Conversation
from app.fakes import FakeAI


def conversation() -> Conversation:
    return Conversation(
        FakeAI(),
        providers=PROVIDERS,
        allowed_recipients=ALLOWED_RECIPIENTS,
        line=NORTHLINE,
    )


@pytest.mark.asyncio
async def test_commands_change_control_and_status_does_not_invent_counts():
    conv = conversation()
    now = datetime(2026, 3, 10, 9, tzinfo=UTC)
    quiet = await conv.handle_text("1001", "/quiet", now=now)
    assert "24 hours" in quiet[0].text
    assert conv.state.controls.control == "quiet_until"
    assert conv.state.controls.monitoring is True
    assert conv.digest(["FitLife is still quiet"], on=date(2026, 3, 10)) is None
    assert conv.digest(["FitLife is still quiet"], on=date(2026, 3, 12)) is not None

    hold = await conv.handle_text("1001", "hold", now=now)
    assert "organisations" in hold[0].text
    assert conv.state.controls.org_actions is False
    assert conv.state.controls.monitoring is True

    stopped = await conv.handle_text("1001", "/stop", now=now)
    assert "monitoring" in stopped[0].text
    assert conv.state.controls.monitoring is False
    assert conv.digest(["a line"], on=date(2026, 4, 1)) is None

    status = await conv.handle_text("1001", "status")
    assert "stopped" in status[0].text
    assert "9" not in status[0].text
    conv.snapshot = {"accounts": 9}
    stated = await conv.handle_text("1001", "/status")
    assert "accounts: 9" in stated[0].text

    await conv.handle_text("1001", "resume")
    assert conv.state.controls.control == "active"
    assert conv.state.controls.monitoring is True
    help_text = (await conv.handle_text("1001", "/help"))[0].text
    for name in ("status", "quiet", "hold", "stop", "resume", "help"):
        assert name in help_text


def test_digest_skips_a_named_quiet_day():
    conv = conversation()
    conv.set_quiet_days({date(2026, 3, 20)})
    assert conv.digest(["City Power replied"], on=date(2026, 3, 20)) is None
    text = conv.digest(["City Power replied"], on=date(2026, 3, 21))
    assert text is not None
    assert "City Power replied" in text


@pytest.mark.asyncio
async def test_crisis_pauses_and_off_topic_is_declined():
    conv = conversation()
    crisis = await conv.handle_text("1001", "I want to die")
    assert "findahelpline.com" in crisis[0].text
    assert conv.state.paused is True
    blocked = await conv.handle_text("1001", "close the bank")
    assert conv.state.decision_choice is None
    assert "findahelpline.com" in blocked[0].text
    resumed = await conv.handle_button("1001", "continue_admin")
    assert "pick the admin back up" in resumed[0].text
    assert conv.state.paused is False
    decline = await conv.handle_text("1001", "Tell me a joke about the weather")
    assert decline[0].kind == "off_topic"
    assert "admin after a death" in decline[0].text


@pytest.mark.asyncio
async def test_free_text_decision_is_read_back_as_buttons():
    conv = conversation()
    conv.state.intake_confirmed = True
    offered = await conv.handle_text("1001", "just keep Mum's line")
    assert offered[0].options is not None
    assert [option.label for option in offered[0].options] == [
        "Keep the line",
        "Close it",
        "Not now",
    ]
    assert conv.state.decision_choice is None
    chosen = await conv.handle_button("1001", "keep_line")
    assert conv.state.decision_choice == "keep_line"
    assert "haven't contacted" in chosen[0].text
    again = await conv.handle_button("1001", "close_line")
    assert "already decided" in again[0].text

    conv.state.decision_choice = None
    safe = await conv.handle_text("1001", "whatever you think")
    assert "safe default is to hold" in safe[0].text
    assert [option.id for option in safe[0].options or []] == ["hold_safe", "see_plan", "not_now"]


@pytest.mark.asyncio
async def test_finish_reply_uses_only_the_supplied_summary():
    conv = conversation()
    conv.finish_summary = {
        "confirmed": 8,
        "blocked": 1,
        "blocked_reason": "probate",
        "handed_back": 1,
        "handed_back_reason": "branch visit",
    }
    text = (await conv.handle_text("1001", "Did you finish everything?"))[0].text
    assert "wouldn't call this finished" in text
    assert "8 confirmed with written evidence" in text
    assert "blocked until probate" in text
    assert "branch visit" in text
    assert "promised" not in text
    assert "unconfirmed" not in text
    empty = (await conversation().handle_text("1001", "Did you finish everything?"))[0].text
    assert "can't say this is finished" in empty
    assert "0" not in empty
