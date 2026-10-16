"""One family send and one provider reply. The live script belongs in the handoff.

This function prints nothing and reads no tokens. Callers pass mailbox objects.
"""

from __future__ import annotations

from app.contracts import Mailbox, SendRequest

SMOKE_REF = "AW-SMOKE-1"


async def mail_smoke(
    family: Mailbox,
    providers: Mailbox,
    *,
    family_address: str,
    providers_address: str,
) -> dict[str, object]:
    """Send one smoke email and one reply. The result contains ids, not secrets."""
    text = (
        "Smoke check from the family mailbox.\n\n"
        "Prepared by Afterward, an AI assistant, on behalf of Sara Malik (as stated).\n\n"
        f"Ref {SMOKE_REF}"
    )
    sent = await family.send(
        SendRequest(
            mailbox=family_address,
            to_addrs=[providers_address],
            subject="Afterward smoke check",
            text=text,
            from_name="Afterward",
            footer_ref=SMOKE_REF,
        )
    )
    reply = await providers.send(
        SendRequest(
            mailbox=providers_address,
            to_addrs=[family_address],
            subject="Re: Afterward smoke check",
            text="Received the smoke check.",
            thread_id=sent.thread_id,
            in_reply_to=sent.rfc_message_id,
            references=[sent.rfc_message_id],
            from_name="Northline Mobile (demo)",
            footer_ref="",
        )
    )
    found = await family.search_sent(family_address, SMOKE_REF)
    return {
        "family_gmail_id": sent.gmail_id,
        "providers_gmail_id": reply.gmail_id,
        "thread_id": sent.thread_id,
        "reconciled": found is not None,
    }
