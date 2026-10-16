"""The Malik skeleton inserts declared providers and separate account references."""

import pytest
from sqlalchemy import func, select

from app.demo.seed import plus_address, seed_malik
from app.models import Account, Member, ProviderProfile


def test_plus_address_keeps_the_tag():
    assert plus_address("providers.demo@example.com", "northline") == (
        "providers.demo+northline@example.com"
    )


@pytest.mark.db
def test_seed_malik_case_providers_and_accounts(db_session):
    case = seed_malik(db_session, providers_mailbox="providers.demo@example.com")
    assert case.ref == "AW-1042"
    assert case.deceased_name == "Yusuf Malik"
    assert case.is_demo is True
    assert case.clock_offset_s == 0
    members = db_session.scalars(select(Member).where(Member.case_id == case.id)).all()
    assert {member.name: member.role.value for member in members} == {
        "Sara Malik": "owner",
        "Amina Malik": "household",
    }
    assert all("stated" not in member.stated_role_text for member in members)
    profiles = db_session.scalars(select(ProviderProfile)).all()
    assert len(profiles) == 5
    northline = next(profile for profile in profiles if profile.name == "Northline Mobile")
    assert northline.approved_recipients == [
        "bereavement@northline.example",
        "providers.demo+northline@example.com",
    ]
    assert northline.response_window_bd == 5
    fitlife = next(profile for profile in profiles if profile.name == "FitLife Gym")
    assert fitlife.response_window_bd == 10
    accounts = db_session.scalars(select(Account).where(Account.case_id == case.id)).all()
    assert len(accounts) == 9
    refs = {account.account_ref for account in accounts}
    assert refs == {
        "4417",
        "2290",
        "0932",
        "CP-77120",
        "SB-88213",
        "FL-5531",
        "HW-20418",
        "ML-6610",
        "PB-3017",
    }
    northline_accounts = [
        account for account in accounts if account.account_ref in {"4417", "2290"}
    ]
    assert len({account.id for account in northline_accounts}) == 2
    assert db_session.scalar(select(func.count()).select_from(Account)) == 9
