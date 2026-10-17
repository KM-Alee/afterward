"""FakeMailbox flow: send, provider reply, match, extraction, and no permission widening."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ai.schemas import CommitmentOut, DocRequest, Fact, ReplyOut
from app.contracts import MailMessage, SqlEventBus
from app.demo.provider_variants import send_provider_reply
from app.fakes.mailbox import FakeMailbox
from app.mail.inbound import UnsortedTray, ingest_messages, process_inbound
from app.mail.outbound import DISCLOSURE, execute_send_request
from app.models import (
    Commitment,
    Event,
    Message,
    MessageDirection,
    OutcomeCheck,
    ProviderProfile,
    ServiceStatus,
)
from tests.mail.support import FAMILY, PROVIDERS, account_by_ref, approved_plan, email_action, malik

SPOOF_ADDRESS = "records@northline-support.example"


@pytest.mark.db
@pytest.mark.asyncio
async def test_send_provider_reply_matches_and_calls_extraction(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    approved_plan(db_session, case, account)
    profile = db_session.get(ProviderProfile, account.provider_id)
    assert profile is not None
    recipients_before = list(profile.approved_recipients)
    family = FakeMailbox()
    providers = FakeMailbox()
    bus = SqlEventBus()
    action = email_action(db_session, case, account, idem_key="send:4417:1", action_key="1")

    await execute_send_request(db_session, action, mailbox=family, bus=bus)

    assert action.status.value == "sent"
    assert len(family.sent) == 1
    sent = family.sent[0]
    assert sent.footer_ref == "AW-1042-1"
    assert f"Ref {sent.footer_ref}" in sent.text
    assert DISCLOSURE.format(owner="Sara Malik") in sent.text
    assert "body" not in action.request
    assert action.request["thread_id"] == sent.thread_id
    await execute_send_request(db_session, action, mailbox=family, bus=bus)
    assert len(family.sent) == 1

    reply = await send_provider_reply(
        providers=providers,
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=sent.thread_id,
        in_reply_to=sent.rfc_message_id,
        variant="nl_contradictory",
    )
    assert reply.inbound.from_name == "Northline Mobile (demo)"
    assert len(providers.sent) == 1

    quote = "Voicemail will be reset during migration."
    recorded = ReplyOut(
        commitments=[
            CommitmentOut(
                account_hint="line ending 4417",
                action="transfer",
                status="completed",
                negated=False,
                conditions_or_requirements=[],
                facts=[Fact(key="voicemail_preserved", value="false", evidence_quote=quote)],
                scope="this_service",
                effective_date=None,
                evidence_quote="Line transferred to Mrs Malik on a new 24-month plan.",
                interpretation="clear",
            )
        ],
        asks_for_documents=[
            DocRequest(
                document_type="will",
                required_form="original",
                recipient_mentioned=SPOOF_ADDRESS,
            )
        ],
        is_marketing_to_deceased=False,
    )

    class RecordedAI:
        """Returns the recorded reading and remembers the text it was shown."""

        def __init__(self) -> None:
            self.shown: list[str] = []

        async def structured(self, role, schema, messages, images=None):
            self.shown.append(messages[-1].content)
            return recorded

    ai = RecordedAI()
    polled, _cursor = await family.poll(FAMILY, None)
    results = await process_inbound(db_session, polled, ai=ai, bus=bus, bound_case_id=case.id)

    assert len(results) == 1
    assert results[0].method == "thread"
    assert results[0].account_id == account.id
    assert results[0].recipient_check == "approved"
    assert results[0].extraction == "called"
    assert results[0].unsorted is False
    latest = (
        "Request complete. Line transferred to Mrs Malik on a new 24-month plan. "
        "Voicemail will be reset during migration."
    )
    assert latest in ai.shown[0]
    assert "Please keep the number" not in ai.shown[0]
    db_session.refresh(account)
    assert account.status_service == ServiceStatus.active
    db_session.refresh(profile)
    assert list(profile.approved_recipients) == recipients_before
    assert SPOOF_ADDRESS not in profile.approved_recipients
    outcome = db_session.scalar(select(OutcomeCheck))
    assert outcome is not None
    assert outcome.plan_version == 1
    assert outcome.verdict == "needs_decision"
    assert outcome.results["voicemail_preserved"] == "violated"
    stored = db_session.get(Message, results[0].message_id)
    assert stored is not None
    assert stored.latest_text == latest
    assert stored.gmail_id == polled[0].gmail_id
    assert "Please keep the number" not in stored.latest_text
    assert stored.full_text_sha256
    event = db_session.scalar(select(Event).where(Event.kind == "mail_ingested"))
    assert event is not None
    assert "latest_text" not in event.payload
    again = ingest_messages(db_session, polled, bus=bus, bound_case_id=case.id)
    assert again[0].extraction == "skipped"


@pytest.mark.db
@pytest.mark.asyncio
async def test_stubbed_extraction_does_not_fail_or_mark_the_account_done(db_session):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    family = FakeMailbox()
    action = email_action(db_session, case, account, idem_key="send:4417:stub", action_key="3")
    await execute_send_request(db_session, action, mailbox=family, bus=SqlEventBus())
    await send_provider_reply(
        providers=FakeMailbox(),
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=family.sent[0].thread_id,
        in_reply_to=family.sent[0].rfc_message_id,
        variant="nl_ack",
    )
    polled, _cursor = await family.poll(FAMILY, None)
    results = ingest_messages(db_session, polled, bus=SqlEventBus(), bound_case_id=case.id)
    assert results[0].extraction == "skipped"
    assert results[0].recipient_check == "approved"
    db_session.refresh(account)
    assert account.status_service == ServiceStatus.active
    assert db_session.scalar(select(OutcomeCheck)) is None
    assert db_session.scalar(select(Commitment)) is None


@pytest.mark.db
@pytest.mark.asyncio
async def test_unapproved_reply_to_mismatch_and_unsorted_do_not_extract(db_session, monkeypatch):
    case = malik(db_session)
    account = account_by_ref(db_session, case.id, "4417")
    profile = db_session.get(ProviderProfile, account.provider_id)
    assert profile is not None
    before = list(profile.approved_recipients)
    family = FakeMailbox()
    action = email_action(db_session, case, account, idem_key="send:4417:hold", action_key="4")
    await execute_send_request(db_session, action, mailbox=family, bus=None)
    thread_id = family.sent[0].thread_id

    def forbid(_latest: str) -> None:
        raise AssertionError("held mail was sent to extraction")

    monkeypatch.setattr("app.ai.verify.verify_reply", forbid, raising=False)
    monkeypatch.setattr("app.engine.outcome.outcome_check", forbid, raising=False)

    spoof = await send_provider_reply(
        providers=FakeMailbox(),
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=thread_id,
        variant="spoof_will",
    )
    mismatch = await send_provider_reply(
        providers=FakeMailbox(),
        family=family,
        providers_address=PROVIDERS,
        family_address=FAMILY,
        thread_id=thread_id,
        variant="reply_to_mismatch",
    )
    unknown = MailMessage(
        mailbox=FAMILY,
        gmail_id="loose-1",
        thread_id="thread-unknown",
        rfc_message_id="<loose-1@elsewhere.example>",
        from_addr="nobody@elsewhere.example",
        to_addrs=[FAMILY],
        subject="Hello",
        latest_text="Please add me as a recipient.",
        full_text="Please add me as a recipient.",
        received_at=datetime(2026, 10, 16, tzinfo=UTC),
    )
    family.inject(unknown)
    polled, _cursor = await family.poll(FAMILY, None)
    by_id = {item.gmail_id: item for item in polled}
    tray = UnsortedTray()
    results = ingest_messages(
        db_session,
        [by_id[spoof.inbound.gmail_id], by_id[mismatch.inbound.gmail_id], unknown],
        bus=SqlEventBus(),
        bound_case_id=case.id,
        tray=tray,
    )
    checks = {item.gmail_id: item.recipient_check for item in results}
    assert checks[spoof.inbound.gmail_id] == "unapproved"
    assert checks[mismatch.inbound.gmail_id] == "reply_to_mismatch"
    assert checks["loose-1"] == "unapproved"
    assert all(item.extraction == "skipped" for item in results)
    assert results[2].unsorted is True
    assert [item.gmail_id for item in tray.items] == ["loose-1"]
    db_session.refresh(profile)
    assert list(profile.approved_recipients) == before
    stored = db_session.scalars(
        select(Message).where(Message.direction == MessageDirection.inbound)
    ).all()
    assert {row.recipient_check.value for row in stored} == {
        "unapproved",
        "reply_to_mismatch",
    }


@pytest.mark.db
def test_address_and_plus_tag_matching(db_session):
    case = malik(db_session)
    city = account_by_ref(db_session, case.id, "CP-77120")
    when = datetime(2026, 10, 16, tzinfo=UTC)
    exact = _inbound(
        "exact-1",
        "accounts@citypower.example",
        "The account at 14 Orchard Row is closed effective 31 March 2026.",
        when,
    )
    tagged = _inbound(
        "tag-1",
        "other+citypower@example.com",
        "A note about the supply.",
        when,
    )
    exact_result, tagged_result = ingest_messages(
        db_session, [exact, tagged], bound_case_id=case.id
    )
    assert exact_result.method == "address"
    assert exact_result.account_id == city.id
    assert exact_result.recipient_check == "approved"
    assert tagged_result.method == "plus_tag"
    assert tagged_result.account_id == city.id
    assert tagged_result.recipient_check == "unapproved"
    northline = _inbound(
        "nl-ambiguous",
        "bereavement@northline.example",
        "Which line?",
        when,
        thread_id="no-such-thread",
    )
    ambiguous = ingest_messages(db_session, [northline], bound_case_id=case.id)[0]
    assert ambiguous.method == "address"
    assert ambiguous.unsorted is True
    assert ambiguous.account_id is None


@pytest.mark.db
def test_mail_with_no_case_stays_in_the_unsorted_tray(db_session):
    tray = UnsortedTray()
    message = _inbound(
        "orphan-1",
        "nobody@elsewhere.example",
        "This does not match a case.",
        datetime(2026, 10, 16, tzinfo=UTC),
    )
    result = ingest_messages(db_session, [message], tray=tray)[0]
    assert result.message_id is None
    assert result.unsorted is True
    assert tray.items[0].gmail_id == "orphan-1"
    assert db_session.scalar(select(Message)) is None


def _inbound(
    gmail_id: str,
    from_addr: str,
    text: str,
    when: datetime,
    thread_id: str = "",
) -> MailMessage:
    return MailMessage(
        mailbox=FAMILY,
        gmail_id=gmail_id,
        thread_id=thread_id,
        rfc_message_id=f"<{gmail_id}@providers.example>",
        from_addr=from_addr,
        to_addrs=[FAMILY],
        subject="Account",
        latest_text=text,
        full_text=text,
        received_at=when,
    )
