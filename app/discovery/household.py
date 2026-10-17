"""Connected inbox search. Headers first; a message is read only after its owner ticks it.

A family member connects either a household inbox they own or Yusuf's own mailbox with
access they already hold (stated authority required, read-only, never used to send).
The query is built here from the case, so the model can narrow a search but never widen it.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.contracts import MailMessage

SCOPE_TERMS = (
    "bill",
    "invoice",
    "statement",
    "renewal",
    '"direct debit"',
    "membership",
    "policy",
    "subscription",
    '"your account"',
)
MAX_HEADERS = 25
_SAFE_TERM = re.compile(r"[^A-Za-z0-9 .,'&@-]")


class HeaderSearch(Protocol):
    """A mailbox that can list headers without bodies, then fetch one message."""

    async def search_headers(
        self, mailbox: str, query: str, limit: int
    ) -> list[dict[str, str]]: ...

    async def get(self, mailbox: str, gmail_id: str) -> MailMessage: ...


@dataclass(frozen=True)
class MailHeader:
    """From, subject and date. No body."""

    id: str
    sender: str
    subject: str
    date: str


class NotTicked(PermissionError):
    """A read was asked for a message the inbox owner has not ticked."""


class NotOwner(PermissionError):
    """Only the person who connected the inbox can choose what is read."""


class AuthorityMissing(PermissionError):
    """His own mailbox needs a stated authority from the family member who connected it."""


HOUSEHOLD = "household"
DECEASED = "deceased"


def _clean(term: str) -> str:
    return " ".join(_SAFE_TERM.sub(" ", term).split())


def scope_query(
    names: Sequence[str], address: str | None, *, years: int = 3, narrow: Sequence[str] = ()
) -> str:
    """Mail naming him or the house, about an account, in the window. Narrowing is ANDed."""
    anchors = [f'"{_clean(item)}"' for item in [*names, address or ""] if _clean(item)]
    if not anchors:
        raise ValueError("A household search needs his name or the address")
    parts = [f"({' OR '.join(anchors)})", f"({' OR '.join(SCOPE_TERMS)})"]
    parts += [f'"{_clean(term)}"' for term in narrow if _clean(term)]
    parts.append(f"newer_than:{max(1, min(years, 10))}y")
    return " ".join(parts)


@dataclass
class HouseholdScan:
    """One connected inbox, owned by one family member, scoped to one case."""

    client: HeaderSearch
    mailbox: str
    owner: str
    names: tuple[str, ...]
    address: str | None = None
    years: int = 3
    account_of: str = HOUSEHOLD
    stated_authority: str = ""
    headers: dict[str, MailHeader] = field(default_factory=dict)
    ticked: set[str] = field(default_factory=set)
    read: set[str] = field(default_factory=set)
    searches: int = 0
    last_query: str = ""

    def __post_init__(self) -> None:
        if self.account_of not in {HOUSEHOLD, DECEASED}:
            raise ValueError("account_of must be household or deceased")
        if self.account_of == DECEASED and not self.stated_authority.strip():
            raise AuthorityMissing("Say on what authority you connected his mailbox")

    @property
    def can_send(self) -> bool:
        """A connected search mailbox is read-only. Sends use the case mailbox only."""
        return False

    async def search(self, narrow: Sequence[str] = ()) -> list[MailHeader]:
        """List headers in scope. Results add to what was already listed."""
        query = scope_query(self.names, self.address, years=self.years, narrow=narrow)
        rows = await self.client.search_headers(self.mailbox, query, MAX_HEADERS)
        self.searches += 1
        self.last_query = query
        found: list[MailHeader] = []
        for row in rows[:MAX_HEADERS]:
            header = MailHeader(
                id=str(row.get("id", "")),
                sender=str(row.get("from", "")),
                subject=str(row.get("subject", "")),
                date=str(row.get("date", "")),
            )
            if header.id:
                self.headers[header.id] = header
                found.append(header)
        return found

    def tick(self, ids: Sequence[str], *, by: str) -> list[str]:
        """The owner chooses what may be read. Unknown ids are ignored."""
        if by != self.owner:
            raise NotOwner("Only the inbox owner can choose what is read")
        chosen = [item for item in ids if item in self.headers]
        self.ticked.update(chosen)
        return chosen

    def tick_numbers(self, numbers: Sequence[int], *, by: str) -> list[str]:
        """Tick by the 1-based numbers shown in the chat list."""
        listed = self.listing()
        ids = [listed[n - 1].id for n in numbers if 1 <= n <= len(listed)]
        return self.tick(ids, by=by)

    def listing(self) -> list[MailHeader]:
        return list(self.headers.values())

    async def read_message(self, message_id: str) -> str:
        """Latest text of one ticked message. Anything else is refused."""
        if message_id not in self.ticked:
            raise NotTicked("That message was not ticked by the inbox owner")
        message = await self.client.get(self.mailbox, message_id)
        self.read.add(message_id)
        return message.latest_text or message.full_text

    async def read_ticked(self) -> list[tuple[MailHeader, str]]:
        out: list[tuple[MailHeader, str]] = []
        for message_id in sorted(self.ticked - self.read):
            out.append((self.headers[message_id], await self.read_message(message_id)))
        return out

    def coverage_line(self) -> str | None:
        if not self.searches:
            return None
        matched = len(self.headers)
        read = len(self.read)
        if self.account_of == DECEASED:
            where = (
                "Yusuf's own inbox, connected read-only by a family member "
                f"(stated: {self.stated_authority.strip()})"
            )
        else:
            where = "Household inbox"
        return (
            f"{where}: {matched} messages about accounts, "
            f"{read} read with your OK, {matched - read} not read"
        )
