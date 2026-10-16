"""Shared rows for engine tests. Addresses and names are the synthetic demo case."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountOrigin,
    Case,
    ChannelName,
    Member,
    MemberRole,
    Ownership,
    ProviderProfile,
)


def make_case(session: Session, **overrides: object) -> Case:
    case = Case(
        ref=f"AW-{uuid4().hex[:10]}",
        deceased_name="Yusuf Malik",
        intent_text="Keep the phone and the voicemail.",
        is_demo=True,
        **overrides,
    )
    session.add(case)
    session.flush()
    return case


def make_owner(session: Session, case: Case, *, granted: bool = True) -> Member:
    member = Member(
        case_id=case.id,
        name="Sara Malik",
        role=MemberRole.owner,
        stated_role_text="daughter, as stated",
        channel=ChannelName.web,
        consent={"status": "granted" if granted else "pending"},
    )
    session.add(member)
    session.flush()
    return member


def make_provider(session: Session, **overrides: object) -> ProviderProfile:
    profile = ProviderProfile(
        name=f"Northline {uuid4().hex[:8]}",
        accepted_channels=["email"],
        required_docs=[{"type": "death_certificate", "form": "photo"}],
        response_window_bd=5,
        completion_evidence=["cancellation_confirmation"],
        approved_recipients=["bereavement@northline.example"],
        is_demo=True,
        **overrides,
    )
    session.add(profile)
    session.flush()
    return profile


def make_account(
    session: Session,
    case: Case,
    provider: ProviderProfile | None = None,
    *,
    account_ref: str = "4417",
) -> Account:
    account = Account(
        case_id=case.id,
        provider_id=None if provider is None else provider.id,
        account_ref=account_ref,
        service_label=f"Line ending {account_ref}",
        holder_name="Yusuf Malik",
        origin=AccountOrigin.forwarded,
        origin_evidence="Synthetic",
        ownership=Ownership.confirmed,
    )
    session.add(account)
    session.flush()
    return account
