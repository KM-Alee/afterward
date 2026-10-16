"""Provider console replies use fictional senders and the approved mock bodies."""

import pytest

from app.demo.provider_variants import SENDERS, VARIANTS, send_provider_reply, variant_ids
from app.fakes.mailbox import FakeMailbox

FAMILY = "family.demo@example.com"
PROVIDERS = "providers.demo@example.com"


class RecordingMailbox(FakeMailbox):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    async def send(self, request):
        self.requests.append(request)
        return await super().send(request)


@pytest.mark.asyncio
async def test_variants_send_in_thread_with_the_demo_display_name():
    assert set(variant_ids()) == {
        "nl_contradictory",
        "nl_ack",
        "probate_blocked",
        "nl_certified",
        "cp_april_feb",
        "cp_refund",
        "reply_to_mismatch",
        "spoof_will",
    }
    providers = RecordingMailbox()
    family = FakeMailbox()
    reply = await send_provider_reply(
        providers=providers,
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id="thread-nl",
        in_reply_to="<sent-1@afterward.example>",
        variant="nl_contradictory",
    )
    request = providers.requests[0]
    assert request.from_name == "Northline Mobile (demo)"
    assert request.thread_id == "thread-nl"
    assert request.in_reply_to == "<sent-1@afterward.example>"
    assert request.mailbox == PROVIDERS
    assert "Voicemail will be reset" in request.text
    assert reply.inbound.from_addr == "bereavement@northline.example"
    polled, _cursor = await family.poll(FAMILY, None)
    assert polled[0].gmail_id == reply.inbound.gmail_id
    assert "24-month plan" in VARIANTS["nl_contradictory"]["body"]
    assert "probate" in str(VARIANTS["probate_blocked"]["body"])
    assert VARIANTS["cp_april_feb"]["body"].startswith("Invoice dated 2 April 2026")
    assert "refund of $42.00" in str(VARIANTS["cp_refund"]["body"])
    assert VARIANTS["reply_to_mismatch"]["reply_to"] == "notices@northline-mail.example"
    assert VARIANTS["spoof_will"]["from_addr"] == "records@northline-support.example"
    for sender in SENDERS.values():
        assert sender["from_addr"].endswith(".example")


@pytest.mark.asyncio
async def test_free_text_uses_the_provider_sender():
    providers = RecordingMailbox()
    reply = await send_provider_reply(
        providers=providers,
        family=None,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id="thread-cp",
        free_text="The final meter read was 48211.",
        provider_key="citypower",
    )
    assert providers.requests[0].from_name == "City Power (demo)"
    assert reply.inbound.from_addr == "accounts@citypower.example"
    assert reply.inbound.latest_text == "The final meter read was 48211."
    with pytest.raises(ValueError):
        await send_provider_reply(
            providers=providers,
            family=None,
            providers_address=PROVIDERS,
            family_address=FAMILY,
            thread_id="thread-cp",
        )
