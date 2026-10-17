"""Dedupe, snapshots, case-built conversation and the queued send, on real Postgres."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.conversation.demo_malik import (
    AMINA_OGG,
    INVITE_TOKEN,
    SARA_OGG,
    demo_repackager,
    register_malik_fixtures,
)
from app.conversation.live import (
    build_conversation,
    claim_update,
    enqueue_send,
    refresh_scan,
    save_state,
)
from app.engine.demo_case import ensure_demo_case
from app.fakes import FakeAI
from app.fakes.mailbox import FakeMailbox
from app.models import (
    ConversationSnapshot,
    Job,
    MailConnection,
    Member,
    MemberRole,
    ProcessedUpdate,
)

pytestmark = pytest.mark.db


class _Settings:
    public_base_url = "https://afterward.example"


def _ai() -> FakeAI:
    ai = FakeAI()
    register_malik_fixtures(ai)
    return ai


def test_claim_update_is_true_once_per_channel(db_session):
    assert claim_update(db_session, 41) is True
    assert claim_update(db_session, 41) is False
    assert claim_update(db_session, 41, channel="whatsapp") is True
    rows = db_session.scalars(select(ProcessedUpdate).where(ProcessedUpdate.update_id == "41"))
    assert len(rows.all()) == 2


def test_conversation_is_built_from_the_case_rows(db_session):
    case_id = ensure_demo_case(db_session)
    conv = build_conversation(db_session, _Settings(), _ai(), case_id=case_id, runner=None)
    assert conv is not None and conv.case_id == case_id
    assert "Northline Mobile" in conv.providers
    assert conv.providers["Northline Mobile"].recipient == "bereavement@northline.example"
    assert "death certificate (photo)" in conv.providers["Northline Mobile"].documents
    assert conv.line.account_ref == "4417"
    assert conv.allowed_recipients and "intruder@" not in str(conv.allowed_recipients)
    assert conv.connect_url == "https://afterward.example/family/onboarding"
    assert conv.scan is None
    assert conv.case_date is not None and conv.case_date.year == 2026


def test_unknown_case_builds_nothing(db_session):
    from uuid import uuid4

    assert build_conversation(db_session, _Settings(), _ai(), case_id=uuid4(), runner=None) is None


@pytest.mark.asyncio
async def test_snapshot_survives_a_restart(db_session):
    case_id = ensure_demo_case(db_session)
    ai = _ai()
    conv = build_conversation(db_session, _Settings(), ai, case_id=case_id, runner=None)
    conv.runner = demo_repackager
    voice = await conv.handle_voice("1001", SARA_OGG)
    assert voice[0].kind == "intake_card"
    await conv.handle_button("1001", "confirm_intake")
    await conv.handle_text("2002", f"/start {INVITE_TOKEN}")
    conv.ask_dependency("2002")
    assert save_state(db_session, conv) is True
    db_session.flush()
    assert db_session.get(ConversationSnapshot, case_id) is not None

    again = build_conversation(db_session, _Settings(), _ai(), case_id=case_id, runner=None)
    assert again.state.intake_confirmed is True
    assert again.state.owner_sender == "1001"
    assert again.state.members["2002"].role == "household"
    assert again.state.open_dependency == {"2002": "4417"}
    assert again.state.intake == conv.state.intake


def test_scan_attaches_for_an_active_connection_and_drops_on_revoke(db_session):
    case_id = ensure_demo_case(db_session)
    owner = db_session.scalar(
        select(Member).where(Member.case_id == case_id, Member.role == MemberRole.owner)
    )
    owner.channel_user_id = "1001"
    conv = build_conversation(db_session, _Settings(), _ai(), case_id=case_id, runner=None)
    assert conv.scan is None
    row = MailConnection(
        case_id=case_id,
        connected_by_member_id=owner.id,
        owner_label="Sara",
        account_of="household",
        address="household@example.test",
    )
    db_session.add(row)
    db_session.flush()
    box = FakeMailbox()
    refresh_scan(db_session, _Settings(), conv, mailbox_factory=lambda _s, _c: box)
    assert conv.scan is not None and conv.scan.owner == "1001"
    assert conv.scan.account_of == "household" and conv.scan.can_send is False
    row.revoked_at = datetime.now(UTC)
    db_session.flush()
    refresh_scan(db_session, _Settings(), conv, mailbox_factory=lambda _s, _c: box)
    assert conv.scan is None


@pytest.mark.asyncio
async def test_household_connection_without_owner_member_still_builds_a_scan(db_session):
    case_id = ensure_demo_case(db_session)
    conv = build_conversation(db_session, _Settings(), _ai(), case_id=case_id, runner=None)
    db_session.add(
        MailConnection(case_id=case_id, account_of="household", address="house@example.test")
    )
    db_session.flush()
    refresh_scan(db_session, _Settings(), conv, mailbox_factory=lambda _s, _c: FakeMailbox())
    assert conv.scan is not None and conv.scan.can_send is False


async def _approved_conversation(db_session):
    case_id = ensure_demo_case(db_session)
    owner = db_session.scalar(
        select(Member).where(Member.case_id == case_id, Member.role == MemberRole.owner)
    )
    owner.channel_user_id = "1001"
    ai = _ai()
    conv = build_conversation(db_session, _Settings(), ai, case_id=case_id, runner=None)
    conv.runner = demo_repackager
    await conv.handle_voice("1001", SARA_OGG)
    await conv.handle_button("1001", "confirm_intake")
    await conv.handle_text("2002", f"/start {INVITE_TOKEN}")
    conv.ask_dependency("2002")
    await conv.handle_voice("2002", AMINA_OGG)
    return case_id, conv


@pytest.mark.asyncio
async def test_approval_enqueues_one_send_request_job(db_session):
    case_id, conv = await _approved_conversation(db_session)
    assert (await conv.handle_button("1001", "approve_plan"))[0].kind == "approval_recorded"
    job_id = enqueue_send(db_session, conv, "1001")
    assert job_id is not None
    job = db_session.get(Job, __import__("uuid").UUID(job_id))
    assert job.kind == "send_request" and job.case_id == case_id
    assert job.payload["outbound"] is True and job.payload["plan_hash"]
    assert job.run_at_case_time <= datetime.now(UTC) + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_enqueue_refuses_a_non_owner_and_a_missing_plan(db_session):
    _case_id, conv = await _approved_conversation(db_session)
    assert enqueue_send(db_session, conv, "2002") is None  # Amina is not the owner
    conv.state.plan = None
    assert enqueue_send(db_session, conv, "1001") is None


def test_unused_names():
    assert demo_repackager
