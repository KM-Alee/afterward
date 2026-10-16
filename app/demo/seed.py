"""Day-0 Malik skeleton: one demo case, five declared providers, nine account references.

Addresses are fictional. A configured providers mailbox adds a plus-address next to
the declared `.example` recipient. Incoming mail can never add a recipient here.
"""

from datetime import UTC, date, datetime

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

DEMO_CASE_REF = "AW-1042"
CHECKED_AT = datetime(2026, 10, 16, tzinfo=UTC)

PROVIDERS: tuple[dict[str, object], ...] = (
    {
        "key": "northline",
        "name": "Northline Mobile",
        "accepted_channels": ["email"],
        "required_info": [
            "deceased name",
            "date of death",
            "account reference",
            "requested action",
        ],
        "required_docs": [{"type": "death_certificate", "form": "photo"}],
        "response_window_bd": 5,
        "completion_evidence": ["new_holder", "number_kept", "voicemail_preserved"],
        "approved_address": "bereavement@northline.example",
        "plus_tag": "northline",
    },
    {
        "key": "crescent",
        "name": "Crescent Bank",
        "accepted_channels": ["branch", "secure_message"],
        "required_info": ["deceased name", "date of death", "account reference"],
        "required_docs": [{"type": "death_certificate", "form": "certified_copy"}],
        "response_window_bd": 10,
        "completion_evidence": ["account_status_letter"],
        "approved_address": "bereavement@crescentbank.example",
        "plus_tag": "crescent",
    },
    {
        "key": "citypower",
        "name": "City Power",
        "accepted_channels": ["email"],
        "required_info": ["service address", "account reference"],
        "required_docs": [],
        "response_window_bd": 5,
        "completion_evidence": ["closure_confirmation", "final_meter_read"],
        "approved_address": "accounts@citypower.example",
        "plus_tag": "citypower",
    },
    {
        "key": "streambox",
        "name": "StreamBox",
        "accepted_channels": ["email"],
        "required_info": ["account reference"],
        "required_docs": [],
        "response_window_bd": 3,
        "completion_evidence": ["cancellation_confirmation"],
        "approved_address": "help@streambox.example",
        "plus_tag": "streambox",
    },
    {
        "key": "fitlife",
        "name": "FitLife Gym",
        "accepted_channels": ["email"],
        "required_info": ["membership reference"],
        "required_docs": [{"type": "death_certificate", "form": "photo"}],
        "response_window_bd": 10,
        "completion_evidence": ["cancellation_confirmation"],
        "approved_address": "members@fitlife.example",
        "plus_tag": "fitlife",
    },
)

ACCOUNTS: tuple[dict[str, object], ...] = (
    {
        "provider_key": "northline",
        "account_ref": "4417",
        "service_label": "Mobile line ending 4417",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.forwarded,
        "origin_evidence": "Forwarded email",
        "ownership": Ownership.confirmed,
    },
    {
        "provider_key": "northline",
        "account_ref": "2290",
        "service_label": "Mobile line ending 2290",
        "holder_name": "",
        "origin": AccountOrigin.photo,
        "origin_evidence": "Photo of a bill; name not shown",
        "ownership": Ownership.unconfirmed,
    },
    {
        "provider_key": "crescent",
        "account_ref": "0932",
        "service_label": "Current account ending 0932",
        "holder_name": "Y. Malik",
        "origin": AccountOrigin.forwarded,
        "origin_evidence": "Forwarded email; may be joint",
        "ownership": Ownership.unconfirmed,
    },
    {
        "provider_key": "citypower",
        "account_ref": "CP-77120",
        "service_label": "Electricity, 14 Orchard Row",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.photo,
        "origin_evidence": "Photo of a bill",
        "ownership": Ownership.confirmed,
    },
    {
        "provider_key": "streambox",
        "account_ref": "SB-88213",
        "service_label": "Streaming subscription",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.forwarded,
        "origin_evidence": "Forwarded email",
        "ownership": Ownership.confirmed,
    },
    {
        "provider_key": "fitlife",
        "account_ref": "FL-5531",
        "service_label": "Membership FL-5531",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.forwarded,
        "origin_evidence": "Forwarded email",
        "ownership": Ownership.confirmed,
    },
    {
        "provider_key": None,
        "account_ref": "HW-20418",
        "service_label": "Water, 14 Orchard Row",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.photo,
        "origin_evidence": "Photo of a bill; no declared profile",
        "ownership": Ownership.confirmed,
    },
    {
        "provider_key": None,
        "account_ref": "ML-6610",
        "service_label": "Policy letter",
        "holder_name": "",
        "origin": AccountOrigin.photo,
        "origin_evidence": "Photo of a letter; name partly hidden; no declared profile",
        "ownership": Ownership.unconfirmed,
    },
    {
        "provider_key": None,
        "account_ref": "PB-3017",
        "service_label": "Book club subscription",
        "holder_name": "Yusuf Malik",
        "origin": AccountOrigin.forwarded,
        "origin_evidence": "Forwarded email; web form only, no declared profile",
        "ownership": Ownership.confirmed,
    },
)


def plus_address(mailbox: str, tag: str) -> str:
    """Build a Gmail-style plus address. The mailbox must already be a single address."""
    local, domain = mailbox.split("@", 1)
    return f"{local}+{tag}@{domain}"


def seed_malik(session: Session, *, providers_mailbox: str = "") -> Case:
    """Insert the demo case. Does not commit. Pass a providers mailbox to add plus-addresses."""
    case = Case(
        ref=DEMO_CASE_REF,
        deceased_name="Yusuf Malik",
        date_of_death=date(2026, 3, 3),
        intent_text=(
            "I want to stop the bills that don't matter, but keep Mum's phone, and his voicemail."
        ),
        intent={
            "keep": ["Mum's phone", "Dad's voicemail"],
            "stop": ["Bills nobody needs"],
            "protect": ["His voice on the voicemail"],
        },
        is_demo=True,
    )
    session.add(case)
    session.flush()
    session.add_all(
        [
            Member(
                case_id=case.id,
                name="Sara Malik",
                role=MemberRole.owner,
                stated_role_text="his daughter; handling the estate",
                channel=ChannelName.telegram,
                consent={"status": "pending"},
            ),
            Member(
                case_id=case.id,
                name="Amina Malik",
                role=MemberRole.household,
                stated_role_text="his wife; lives in the family home",
                channel=ChannelName.telegram,
                consent={"status": "pending"},
            ),
        ]
    )
    profile_ids: dict[str, object] = {}
    for row in PROVIDERS:
        recipients = [str(row["approved_address"])]
        if providers_mailbox:
            recipients.append(plus_address(providers_mailbox, str(row["plus_tag"])))
        profile = ProviderProfile(
            name=str(row["name"]),
            accepted_channels=list(row["accepted_channels"]),  # type: ignore[arg-type]
            required_info=list(row["required_info"]),  # type: ignore[arg-type]
            required_docs=list(row["required_docs"]),  # type: ignore[arg-type]
            response_window_bd=int(row["response_window_bd"]),  # type: ignore[arg-type]
            completion_evidence=list(row["completion_evidence"]),  # type: ignore[arg-type]
            approved_recipients=recipients,
            is_demo=True,
            source_url="",
            checked_at=CHECKED_AT,
        )
        session.add(profile)
        session.flush()
        profile_ids[str(row["key"])] = profile.id
    for row in ACCOUNTS:
        provider_key = row["provider_key"]
        session.add(
            Account(
                case_id=case.id,
                provider_id=None if provider_key is None else profile_ids[str(provider_key)],  # type: ignore[arg-type]
                account_ref=str(row["account_ref"]),
                service_label=str(row["service_label"]),
                holder_name=str(row["holder_name"]),
                origin=row["origin"],  # type: ignore[arg-type]
                origin_evidence=str(row["origin_evidence"]),
                ownership=row["ownership"],  # type: ignore[arg-type]
                next_step={"owner": "family", "action": "Confirm this candidate", "due_date": None},
            )
        )
    session.flush()
    return case
