"""An unhealthy mailbox must not cancel the poll that would make it healthy again."""

from app.engine import jobs


def test_inbox_poll_is_not_gated_on_mailbox_health():
    assert "inbox_poll" not in jobs._MAILBOX_KINDS
    assert "send_request" in jobs._MAILBOX_KINDS
