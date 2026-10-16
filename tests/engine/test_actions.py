"""Uncertain sends are reconciled, and a blind retry is refused."""

import pytest

from app.contracts import SendRequest
from app.engine.actions import (
    reconcile_action,
    record_failed,
    record_sent,
    record_uncertain,
    reserve_action,
    retry_uncertain,
)
from app.engine.errors import BlindRetryForbidden
from app.fakes.mailbox import FakeMailbox
from tests.engine.support import make_case


@pytest.mark.db
async def test_uncertain_send_reconciles_and_does_not_retry_blindly(db_session):
    case = make_case(db_session)
    mailbox = FakeMailbox()
    action = reserve_action(
        db_session,
        case_id=case.id,
        kind="email_send",
        idem_key="email:1",
        request={},
    )
    again = reserve_action(
        db_session,
        case_id=case.id,
        kind="email_send",
        idem_key="email:1",
    )
    assert again.id == action.id
    footer = "Ref AW-action-1"
    await mailbox.send(
        SendRequest(
            mailbox="family",
            to_addrs=["bereavement@northline.example"],
            subject="Request",
            text=f"Please close the line.\n\n{footer}",
            footer_ref=footer,
        )
    )
    record_uncertain(action)
    with pytest.raises(BlindRetryForbidden):
        retry_uncertain(action)
    with pytest.raises(BlindRetryForbidden):
        record_sent(action, "sent-1")
    found = await mailbox.search_sent("family", footer)
    assert reconcile_action(action, found=found is not None, search_completed=True) == "reconciled"
    assert len(mailbox.sent) == 1
    assert action.status.value == "reconciled"


@pytest.mark.db
def test_proven_unsent_may_retry_once(db_session):
    case = make_case(db_session)
    action = reserve_action(db_session, case_id=case.id, kind="email_send", idem_key="email:2")
    record_uncertain(action)
    assert reconcile_action(action, found=False, search_completed=False) == "uncertain"
    assert action.status.value == "uncertain"
    assert reconcile_action(action, found=False, search_completed=True) == "retry_once"
    assert action.status.value == "pending"
    retry_uncertain(action)
    record_uncertain(action)
    assert reconcile_action(action, found=False, search_completed=True) == "uncertain"
    with pytest.raises(BlindRetryForbidden):
        retry_uncertain(action)
    fresh = reserve_action(db_session, case_id=case.id, kind="chat_send", idem_key="chat:1")
    record_failed(fresh)
    assert fresh.status.value == "failed"
