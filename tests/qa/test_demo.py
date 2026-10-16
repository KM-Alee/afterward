"""Demo-consistency checks from AFTERWARD.md section 14.1."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.demo.provider_variants import VARIANTS
from app.demo.seed import seed_malik
from app.discovery.vault import VaultCipher, intake_document
from app.engine.jobs import add_business_days, enqueue, is_due, schedule_followup
from app.engine.outcome import assess_money
from app.engine.plans import approve, revise_plan
from app.models import Autopilot, MoneyItemStatus, ProviderProfile
from tests.engine.support import make_account, make_case, make_owner, make_provider
from tests.web.conftest import login

APPROVED = "members@fitlife.example"


def test_plus_14_days_sends_exactly_one_fitlife_followup(client):
    """FitLife's 10 business-day window means the +14 day jump sends one follow-up."""
    login(client)
    surface = client.app.state.surface
    moved = client.post(
        f"/api/cases/{surface.demo_case_id}/clock",
        data={"advance_days": "14"},
        follow_redirects=True,
    )
    assert moved.status_code == 200
    assert "20 Mar 2026" in moved.text
    followups = [
        record
        for record in surface.mailbox.sent
        if "FL-5531" in record.text or "following up" in record.text.casefold()
    ]
    assert len(followups) == 1


@pytest.mark.db
def test_fitlife_ten_business_days_is_one_followup_inside_fourteen_calendar_days(db_session):
    case = make_case(db_session, autopilot=Autopilot.steady)
    owner = make_owner(db_session, case)
    provider = make_provider(db_session)
    provider.response_window_bd = 10
    account = make_account(db_session, case, provider, account_ref="FL-5531")
    plan = revise_plan(
        db_session,
        case_id=case.id,
        account_id=account.id,
        action="notify",
        conditions=[],
        documents=[],
        recipient=APPROVED,
    )
    approval = approve(
        db_session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=owner.id,
    )
    sent_at = datetime.now(UTC)
    first = schedule_followup(
        db_session,
        case=case,
        account_id=account.id,
        plan=plan,
        approval_id=approval.id,
        sent_at=sent_at,
        window_bd=provider.response_window_bd,
        n=1,
    )
    second = enqueue(
        db_session,
        case_id=case.id,
        kind="followup",
        run_at_case_time=add_business_days(first.run_at_case_time, provider.response_window_bd),
        idem_key=f"followup:{account.id}:planv{plan.version}:n2",
        payload={"plan_id": str(plan.id), "n": 2},
    )
    case.clock_offset_s = 14 * 86400
    db_session.flush()
    assert provider.response_window_bd == 10
    assert is_due(first, case, sent_at) is True
    assert is_due(second, case, sent_at) is False


def test_desk_keeps_northline_as_a_transfer_and_sara_stated(client):
    login(client)
    surface = client.app.state.surface
    page = client.get(f"/desk/{surface.demo_case_id}")
    assert page.status_code == 200
    assert "Move the line to Amina Malik" in page.text
    assert "Reported transferred" in page.text
    assert "handling the estate (as she has told us)" in page.text
    assert "executor" not in page.text.casefold()


def test_phone_photo_stays_a_photo():
    from cryptography.fernet import Fernet

    from app.ai.schemas import DocOut

    document = DocOut(
        doc_type="death_certificate",
        form="certified_copy_held",
        name="Yusuf Malik",
        date_of_death=None,
        certificate_number=None,
        provider="Northline Mobile",
        account_reference="4417",
        amounts=[],
        billing_period=None,
        quotes=["photo"],
        confidence="low",
    )
    item = intake_document(
        doc=document,
        raw_form="certified_copy_held",
        image=b"FICTIONAL-PHOTO",
        cipher=VaultCipher(Fernet.generate_key()),
        source="phone_photo",
    )
    assert item.form == "photo"
    assert item.form != "certified_copy_held"


def test_april_invoice_for_february_service_is_not_a_dispute():
    body = str(VARIANTS["cp_april_feb"]["body"])
    assert "February" in body
    assert "April" in body
    assessment = assess_money(
        kind="charge",
        service_period_start=date(2026, 2, 1),
        closure_effective_date=date(2026, 3, 3),
        date_of_death=date(2026, 3, 3),
    )
    assert assessment.status is MoneyItemStatus.needs_review
    assert assessment.dispute_proposed is False


@pytest.mark.db
def test_seeded_fitlife_window_is_ten_business_days(db_session):
    seed_malik(db_session)
    profile = db_session.scalar(
        select(ProviderProfile).where(ProviderProfile.name == "FitLife Gym")
    )
    assert profile is not None
    assert profile.response_window_bd == 10
