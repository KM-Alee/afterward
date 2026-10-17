"""In-memory threads and Sent mail. History expiry falls back to the full list."""

from app.contracts import MailCursor, MailMessage, MailNotFound, SendRequest, SentRecord


class FakeMailbox:
    """Messages injected or sent here stay in process memory only."""

    def __init__(self) -> None:
        self._messages: dict[tuple[str, str], MailMessage] = {}
        self._order: dict[str, list[str]] = {}
        self._expired: set[str] = set()
        self.sent: list[SentRecord] = []
        self._serial = 0

    def inject(self, message: MailMessage) -> None:
        self._messages[(message.mailbox, message.gmail_id)] = message
        self._order.setdefault(message.mailbox, []).append(message.gmail_id)

    def expire_history(self, mailbox: str) -> None:
        """The next poll treats the stored history cursor as expired."""
        self._expired.add(mailbox)

    async def poll(
        self, mailbox: str, cursor: MailCursor | None
    ) -> tuple[list[MailMessage], MailCursor]:
        ids = self._order.get(mailbox, [])
        expired = mailbox in self._expired or (cursor is not None and cursor.expired)
        if expired or cursor is None or not cursor.history_id:
            start = 0
            self._expired.discard(mailbox)
        else:
            try:
                start = ids.index(cursor.history_id) + 1
            except ValueError:
                start = 0
        found = [self._messages[(mailbox, gmail_id)] for gmail_id in ids[start:]]
        history_id = ids[-1] if ids else None
        return found, MailCursor(history_id=history_id, expired=False)

    async def get(self, mailbox: str, gmail_id: str) -> MailMessage:
        try:
            return self._messages[(mailbox, gmail_id)]
        except KeyError:
            raise MailNotFound("No message for that id") from None

    async def send(self, request: SendRequest) -> SentRecord:
        self._serial += 1
        gmail_id = f"sent-{self._serial}"
        thread_id = request.thread_id or f"thread-{self._serial}"
        rfc_message_id = f"<{gmail_id}@fake.example>"
        record = SentRecord(
            mailbox=request.mailbox,
            gmail_id=gmail_id,
            thread_id=thread_id,
            rfc_message_id=rfc_message_id,
            footer_ref=request.footer_ref,
            text=request.text,
        )
        self.sent.append(record)
        return record

    async def search_headers(self, mailbox: str, query: str, limit: int) -> list[dict[str, str]]:
        """Headers of messages whose text holds any quoted anchor in the query."""
        anchors = [part.lower() for part in query.split('"')[1::2]]
        rows: list[dict[str, str]] = []
        for gmail_id in self._order.get(mailbox, []):
            message = self._messages[(mailbox, gmail_id)]
            haystack = f"{message.subject} {message.full_text}".lower()
            if any(anchor in haystack for anchor in anchors):
                rows.append(
                    {
                        "id": gmail_id,
                        "from": message.from_addr,
                        "subject": message.subject,
                        "date": "",
                    }
                )
        return rows[: max(0, limit)]

    async def search_sent(self, mailbox: str, footer_ref: str) -> SentRecord | None:
        for record in self.sent:
            if record.mailbox == mailbox and footer_ref and footer_ref in record.text:
                return record
        return None
