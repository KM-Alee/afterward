"""Deterministic fakes for AI, mail, channels, the clock and the call session."""

from datetime import UTC, datetime, timedelta

import pytest

from app.ai.schemas import ReplyOut
from app.contracts import (
    CallEvent,
    CallEventKind,
    CallSessionError,
    CallTransport,
    ChatMessage,
    FakeFixtureMissing,
    InboundEvent,
    InboundKind,
    MailCursor,
    MailMessage,
    Option,
    WebhookRejected,
    WebhookRequest,
)
from app.fakes import FakeAI, FakeCallSession, FakeChannel, FakeClock, FakeMailbox


class _Case:
    def __init__(self, offset: int) -> None:
        self.clock_offset_s = offset


def test_clock_adds_only_the_case_offset():
    clock = FakeClock(datetime(2026, 3, 6, 9, 0, tzinfo=UTC))
    assert clock.case_now(_Case(0)) == clock.wall
    assert clock.case_now(_Case(14 * 24 * 3600)) == clock.wall + timedelta(days=14)
    clock.advance(days=1)
    assert clock.case_now(_Case(0)) == datetime(2026, 3, 7, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fake_ai_is_fixture_keyed_and_refuses_to_guess():
    ai = FakeAI()
    messages = [ChatMessage(role="user", content="Request complete.")]
    reply = ReplyOut(
        commitments=[],
        asks_for_documents=[],
        is_marketing_to_deceased=False,
    )
    ai.register_structured("reply_reader", ReplyOut, messages, reply)
    assert await ai.structured("reply_reader", ReplyOut, messages) == reply
    with pytest.raises(FakeFixtureMissing):
        await ai.structured(
            "reply_reader",
            ReplyOut,
            [ChatMessage(role="user", content="different")],
        )
    ai.register_transcript(b"audio", "Yusuf Malik")
    heard = await ai.transcribe(b"audio", mime="audio/webm")
    assert heard.text == "Yusuf Malik"
    assert heard.language == "en"
    chunks = [chunk async for chunk in ai.speak_stream("The number is kept.")]
    assert chunks[0].audio == b"The number is kept."
    assert ai.spoken == ["The number is kept."]


@pytest.mark.asyncio
async def test_mailbox_threads_sent_search_and_history_fallback():
    box = FakeMailbox()
    first = _mail("m1", "We received your request.")
    second = _mail("m2", "A refund of $42 will be processed.")
    box.inject(first)
    found, cursor = await box.poll("family", None)
    assert [item.gmail_id for item in found] == ["m1"]
    box.inject(second)
    found, cursor = await box.poll("family", cursor)
    assert [item.gmail_id for item in found] == ["m2"]
    box.expire_history("family")
    found, cursor = await box.poll("family", MailCursor(history_id="missing", expired=False))
    assert [item.gmail_id for item in found] == ["m1", "m2"]
    assert await box.get("family", "m2") == second
    from app.contracts import SendRequest

    sent = await box.send(
        SendRequest(
            mailbox="family",
            to_addrs=["bereavement@northline.example"],
            subject="Line ending 4417",
            text="Please keep the number.\n\nRef AW-1042-1",
            footer_ref="AW-1042-1",
            thread_id="thread-1",
        )
    )
    assert sent.thread_id == "thread-1"
    assert (await box.search_sent("family", "AW-1042-1")) == sent
    assert await box.search_sent("family", "AW-missing") is None


@pytest.mark.asyncio
async def test_channel_records_sends_and_checks_the_signature():
    channel = FakeChannel()
    await channel.send_text("sara", "hello")
    await channel.send_buttons(
        "sara", "Choose", [Option(id="a", label="Approve"), Option(id="b", label="Not now")]
    )
    with pytest.raises(Exception, match="3 options"):
        await channel.send_buttons(
            "sara",
            "Too many",
            [Option(id=str(i), label=f"N{i}") for i in range(4)],
        )
    channel.inject(InboundEvent(kind=InboundKind.text, sender="sara", text="status"))
    with pytest.raises(WebhookRejected):
        channel.parse_webhook(WebhookRequest(body=b"", headers={}, query={}))
    events = channel.parse_webhook(
        WebhookRequest(body=b"", headers={"X-Channel-Signature": "ok"}, query={})
    )
    assert events[0].text == "status"
    channel.store_media("photo-1", b"img", "image/jpeg")
    assert await channel.fetch_media("photo-1") == (b"img", "image/jpeg")
    assert channel.outbox[0]["kind"] == "text"


@pytest.mark.asyncio
async def test_call_session_queues_and_discards_acceptance():
    call = FakeCallSession()
    assert not hasattr(call, "accept")
    with pytest.raises(CallSessionError):
        await call.play_approved_sentence("We accept.")
    await call.start(CallTransport.browser)
    await call.suspend_acceptance()
    await call.play_approved_sentence("The family accepts the 12-month terms.")
    assert call.played == []
    await call.discard_queued_acceptance()
    await call.resume_acceptance()
    assert call.played == []
    assert call.discarded == ["The family accepts the 12-month terms."]
    await call.play_approved_sentence("Kept.")
    assert call.played == ["Kept."]
    await call.send_typed_turn("The offer changed.")
    assert call.typed_turns == ["The offer changed."]
    call.push_event(CallEvent(kind=CallEventKind.guardrail_tripped, payload={"rule": "commitment"}))
    assert call.events()[0].kind is CallEventKind.guardrail_tripped
    await call.relay_audio_in(b"pcm")
    call.queue_audio_out(b"out")
    heard = [chunk async for chunk in call.relay_audio_out()]
    assert heard == [b"out"]
    await call.stop()
    with pytest.raises(CallSessionError):
        await call.send_typed_turn("too late")


def _mail(gmail_id: str, text: str) -> MailMessage:
    return MailMessage(
        mailbox="family",
        gmail_id=gmail_id,
        thread_id="thread-1",
        rfc_message_id=f"<{gmail_id}@fake.example>",
        from_addr="bereavement@northline.example",
        to_addrs=["family@example.com"],
        subject="Line ending 4417",
        latest_text=text,
        full_text=text,
        received_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
