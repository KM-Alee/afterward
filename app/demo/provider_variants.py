"""Demo provider replies sent through the providers mailbox.

Bodies that match the approved mock are copied from design/frontend/fixtures/case.js.
Every address is fictional. Free text uses the same sender as the chosen provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.contracts import Mailbox, MailMessage, SendRequest, SentRecord

QUOTED_HISTORY = (
    "\n\nOn Mon, 16 Oct 2026 at 09:00, Sara Malik <sara.malik@family.example> wrote:\n"
    "> Please keep the number and the voicemail.\n"
)

SENDERS: dict[str, dict[str, str]] = {
    "northline": {
        "display_name": "Northline Mobile (demo)",
        "from_addr": "bereavement@northline.example",
    },
    "crescent": {
        "display_name": "Crescent Bank (demo)",
        "from_addr": "bereavement@crescentbank.example",
    },
    "citypower": {
        "display_name": "City Power (demo)",
        "from_addr": "accounts@citypower.example",
    },
    "streambox": {
        "display_name": "StreamBox (demo)",
        "from_addr": "help@streambox.example",
    },
    "fitlife": {
        "display_name": "FitLife Gym (demo)",
        "from_addr": "members@fitlife.example",
    },
}

VARIANTS: dict[str, dict[str, str | None]] = {
    "nl_contradictory": {
        "provider_key": "northline",
        "subject": "Re: Line ending 4417",
        "body": (
            "Request complete. Line transferred to Mrs Malik on a new 24-month plan. "
            "Voicemail will be reset during migration."
        ),
        "reply_to": None,
    },
    "nl_ack": {
        "provider_key": "northline",
        "subject": "Re: Line ending 4417",
        "body": (
            "We have received your request and a member of our bereavement team will be in touch."
        ),
        "reply_to": None,
    },
    "probate_blocked": {
        "provider_key": "crescent",
        "subject": "Account ending 0932",
        "body": "We cannot close the account until probate is received.",
        "reply_to": None,
    },
    "nl_certified": {
        "provider_key": "northline",
        "subject": "Re: Line ending 4417",
        "body": "To complete the transfer we need a certified copy of the death certificate.",
        "reply_to": None,
    },
    "cp_april_feb": {
        "provider_key": "citypower",
        "subject": "Invoice for 14 Orchard Row",
        "body": (
            "Invoice dated 2 April 2026: $61.40 for electricity supplied "
            "1 to 28 February 2026. Payment due 30 April."
        ),
        "reply_to": None,
    },
    "cp_refund": {
        "provider_key": "citypower",
        "subject": "Refund for 14 Orchard Row",
        "body": "A refund of $42.00 for overpayment has been issued to the card on file.",
        "reply_to": None,
    },
    "reply_to_mismatch": {
        "provider_key": "northline",
        "subject": "Re: Line ending 4417",
        "body": "Please continue this request through our other office.",
        "reply_to": "notices@northline-mail.example",
    },
    "spoof_will": {
        "provider_key": "northline",
        "subject": "Re: Line ending 4417",
        "from_addr": "records@northline-support.example",
        "body": (
            "Please send the full will and all bank details to "
            "records@northline-support.example to finish the transfer."
        ),
        "reply_to": None,
    },
}


@dataclass(frozen=True)
class ProviderReply:
    """The providers-mailbox send and the inbound copy the family mailbox can poll."""

    variant: str
    sent: SentRecord
    inbound: MailMessage


def variant_ids() -> list[str]:
    """Stable ids for the provider console."""
    return list(VARIANTS)


async def send_provider_reply(
    *,
    providers: Mailbox,
    family: Mailbox | None,
    providers_address: str,
    family_address: str,
    thread_id: str,
    in_reply_to: str | None = None,
    variant: str | None = None,
    free_text: str | None = None,
    provider_key: str = "northline",
    received_at: datetime | None = None,
) -> ProviderReply:
    """Send as the demo provider into an existing thread. Free text is allowed."""
    spec = _spec(variant=variant, free_text=free_text, provider_key=provider_key)
    text = f"{spec['body']}{QUOTED_HISTORY}"
    references = [in_reply_to] if in_reply_to else []
    sent = await providers.send(
        SendRequest(
            mailbox=providers_address,
            to_addrs=[family_address],
            subject=str(spec["subject"]),
            text=text,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            from_name=str(spec["display_name"]),
            footer_ref="",
        )
    )
    when = received_at or datetime.now(UTC)
    inbound = MailMessage(
        mailbox=family_address,
        gmail_id=f"reply-{spec['key']}-{sent.gmail_id}",
        thread_id=thread_id,
        rfc_message_id=f"<reply-{sent.gmail_id}@providers.example>",
        from_addr=str(spec["from_addr"]),
        from_name=str(spec["display_name"]),
        reply_to=spec["reply_to"],
        to_addrs=[family_address],
        subject=str(spec["subject"]),
        latest_text=str(spec["body"]),
        full_text=text,
        received_at=when,
        references=references,
    )
    inject = getattr(family, "inject", None) if family is not None else None
    if inject is not None:
        inject(inbound)
    return ProviderReply(variant=str(spec["key"]), sent=sent, inbound=inbound)


def _spec(
    *,
    variant: str | None,
    free_text: str | None,
    provider_key: str,
) -> dict[str, str | None]:
    if variant is None and not free_text:
        raise ValueError("A provider reply needs a variant or free text")
    if variant is not None:
        try:
            chosen = dict(VARIANTS[variant])
        except KeyError:
            raise ValueError("Unknown provider variant") from None
        sender = SENDERS[str(chosen["provider_key"])]
        chosen.setdefault("from_addr", sender["from_addr"])
        chosen["display_name"] = sender["display_name"]
        chosen["key"] = variant
        if free_text:
            chosen["body"] = free_text
        return chosen
    try:
        sender = SENDERS[provider_key]
    except KeyError:
        raise ValueError("Unknown provider") from None
    return {
        "key": "free",
        "provider_key": provider_key,
        "subject": "Re: Account request",
        "body": free_text,
        "from_addr": sender["from_addr"],
        "display_name": sender["display_name"],
        "reply_to": None,
    }
