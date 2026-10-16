"""The in-process smoke flow sends one message each way and reconciles the marker."""

import pytest

from app.fakes.mailbox import FakeMailbox
from app.mail.smoke import SMOKE_REF, mail_smoke


@pytest.mark.asyncio
async def test_mail_smoke_reconciles_the_family_send():
    family = FakeMailbox()
    providers = FakeMailbox()
    result = await mail_smoke(
        family,
        providers,
        family_address="family.demo@example.com",
        providers_address="providers.demo@example.com",
    )
    assert result["reconciled"] is True
    assert result["thread_id"] == providers.sent[0].thread_id
    assert SMOKE_REF in family.sent[0].text
    assert providers.sent[0].text == "Received the smoke check."
    assert "Sara Malik" in family.sent[0].text
