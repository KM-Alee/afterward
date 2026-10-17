"""Shared helpers for discovery tests."""

from datetime import UTC, datetime

from app.contracts import MailMessage
from app.discovery.household import HouseholdScan
from app.fakes.mailbox import FakeMailbox

BOX = "sara@family.example"


def message(gmail_id: str, subject: str, body: str, sender: str = "billing@northline.example"):
    return MailMessage(
        mailbox=BOX,
        gmail_id=gmail_id,
        thread_id=f"t-{gmail_id}",
        rfc_message_id=f"<{gmail_id}@x>",
        from_addr=sender,
        to_addrs=[BOX],
        subject=subject,
        latest_text=body,
        full_text=body,
        received_at=datetime(2026, 4, 1, tzinfo=UTC),
    )


def mailbox() -> FakeMailbox:
    box = FakeMailbox()
    box.inject(message("m1", "Your bill", "Yusuf Malik account 4417 bill due"))
    box.inject(message("m2", "Statement", "Yusuf Malik statement for gym"))
    return box


def scan(box: FakeMailbox | None = None, **kw) -> HouseholdScan:
    args = dict(
        client=box or mailbox(),
        mailbox=BOX,
        owner="sara",
        names=("Yusuf Malik",),
        address="12 Elm Road",
    )
    args.update(kw)
    return HouseholdScan(**args)


class RecordingSearch:
    """Captures the query the code built."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.gets: list[str] = []

    async def search_headers(self, mailbox, query, limit):
        self.queries.append(query)
        return [{"id": "x1", "from": "a@b.example", "subject": "Bill", "date": ""}]

    async def get(self, mailbox, gmail_id):
        self.gets.append(gmail_id)
        return message(gmail_id, "s", "body")
