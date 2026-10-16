"""Four dimensions stay independent, and the finish summary is written by code."""

from app.engine.status import classify_account, finish_summary, four_dimensions
from app.models import Account, AccountOrigin, DocsStatus, MoneyStatus, Ownership, ServiceStatus


def _account(**overrides) -> Account:
    values = {
        "account_ref": "4417",
        "service_label": "Line",
        "origin": AccountOrigin.manual,
        "ownership": Ownership.confirmed,
        "status_service": ServiceStatus.active,
        "status_money": MoneyStatus.none,
        "status_docs": DocsStatus.none_needed,
        "next_step": {"owner": "afterward", "action": "None", "due_date": None},
    }
    values.update(overrides)
    return Account(**values)


def test_dimensions_can_all_be_open_together():
    account = _account(
        status_service=ServiceStatus.transferred,
        status_money=MoneyStatus.refund_promised,
        status_docs=DocsStatus.requested,
        next_step={"owner": "provider", "action": "Wait for the refund", "due_date": "2026-04-20"},
    )
    snapshot = four_dimensions(account, conditions={"voicemail_preserved": "holding"})
    assert snapshot["service"] == "transferred"
    assert snapshot["money"] == "refund_promised"
    assert snapshot["documents"] == "requested"
    assert snapshot["next_step"]["owner"] == "provider"
    assert snapshot["conditions"]["voicemail_preserved"] == "holding"


def test_finish_summary_counts_each_bucket():
    rows = [
        (_account(status_service=ServiceStatus.closed), True),
        (
            _account(
                status_service=ServiceStatus.acknowledged,
                status_money=MoneyStatus.refund_promised,
            ),
            True,
        ),
        (_account(status_service=ServiceStatus.blocked), True),
        (_account(next_step={"owner": "family", "action": "Branch visit", "due_date": None}), True),
        (_account(ownership=Ownership.unconfirmed), True),
        (_account(status_service=ServiceStatus.closed), False),
    ]
    summary = finish_summary(rows)
    assert summary.confirmed == 1
    assert summary.promised == 1
    assert summary.blocked == 1
    assert summary.handed_back == 1
    assert summary.unconfirmed == 1
    assert summary.open == 1
    assert "1 confirmed with written evidence." in summary.text
    assert "1 promised but not yet evidenced." in summary.text
    assert "1 blocked on a requirement." in summary.text
    assert "1 handed to you." in summary.text
    assert "1 candidate account still unconfirmed." in summary.text
    assert classify_account(rows[-1][0], conditions_hold=False) == "open"
