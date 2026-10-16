"""Gmail mailbox behaviour against an in-memory transport. No network."""

import base64
from email import policy
from email.parser import BytesParser

import pytest

from app.contracts import Mailbox, MailCursor, MailNotFound, SendRequest
from app.mail.errors import DeliveryUncertain, FooterMissing, HistoryExpired
from app.mail.gmail import RECENT_QUERY, GmailMailbox, GoogleGmailTransport, http_status

FAMILY = "family.demo@example.com"


def _resource(gmail_id: str, text: str, *, thread_id: str = "thread-1") -> dict:
    data = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    return {
        "id": gmail_id,
        "threadId": thread_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "City Power (demo) <accounts@citypower.example>"},
                {"name": "To", "value": FAMILY},
                {"name": "Subject", "value": "Re: Account"},
                {"name": "Message-ID", "value": f"<{gmail_id}@providers.example>"},
            ],
            "body": {"data": data},
        },
    }


class Transport:
    """Records Gmail calls and serves synthetic resources."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.history_calls: list[str] = []
        self.sent: list[dict] = []
        self.resources = {
            "m-old": _resource("m-old", "Older note."),
            "m-new": _resource("m-new", "A refund of $42.00 has been issued."),
        }
        self.expire = False
        self.valid = True
        self.missing = False

    def history_list(self, start_history_id: str) -> dict:
        self.history_calls.append(start_history_id)
        if self.expire:
            raise HistoryExpired("Gmail history cursor expired")
        return {
            "historyId": "20",
            "history": [
                {"messagesAdded": [{"message": {"id": "m-new", "labelIds": ["INBOX"]}}]},
                {"messagesAdded": [{"message": {"id": "m-sent", "labelIds": ["SENT"]}}]},
            ],
        }

    def messages_list(self, query: str) -> list[str]:
        self.queries.append(query)
        if query == RECENT_QUERY:
            return ["m-old", "m-new"]
        if query.startswith("in:sent"):
            return ["m-sent-copy"]
        return []

    def messages_get(self, gmail_id: str) -> dict:
        if self.missing or gmail_id not in self.resources:
            raise MailNotFound("No message for that id")
        return self.resources[gmail_id]

    def messages_send(self, body: dict) -> dict:
        self.sent.append(body)
        return {"id": "sent-9", "threadId": body.get("threadId") or "thr-new"}

    def profile_history_id(self) -> str:
        return "50"

    def token_valid(self) -> bool:
        return self.valid


def _box(transport: Transport) -> GmailMailbox:
    return GmailMailbox({FAMILY: transport})


@pytest.mark.asyncio
async def test_history_poll_skips_sent_and_expired_cursor_lists_recent_mail():
    transport = Transport()
    box = _box(transport)
    assert isinstance(box, Mailbox)
    found, cursor = await box.poll(FAMILY, MailCursor(history_id="15"))
    assert [item.gmail_id for item in found] == ["m-new"]
    assert cursor.history_id == "20"
    assert transport.history_calls == ["15"]
    transport.expire = True
    found, cursor = await box.poll(FAMILY, MailCursor(history_id="15"))
    assert [item.gmail_id for item in found] == ["m-old", "m-new"]
    assert cursor.history_id == "50"
    assert transport.queries == [RECENT_QUERY]


@pytest.mark.asyncio
async def test_missing_or_expired_cursor_uses_the_recent_list():
    transport = Transport()
    box = _box(transport)
    await box.poll(FAMILY, None)
    await box.poll(FAMILY, MailCursor(history_id="15", expired=True))
    assert transport.history_calls == []
    assert transport.queries == [RECENT_QUERY, RECENT_QUERY]


@pytest.mark.asyncio
async def test_send_keeps_thread_and_rfc_headers_and_search_finds_the_marker():
    transport = Transport()
    marker = "AW-1042-1"
    text = f"Please keep the number.\n\nRef {marker}"
    transport.resources["m-sent-copy"] = _resource("m-sent-copy", text, thread_id="thread-7")
    box = _box(transport)
    sent = await box.send(
        SendRequest(
            mailbox=FAMILY,
            to_addrs=["providers.demo+northline@example.com"],
            subject="Line ending 4417",
            text=text,
            thread_id="thread-7",
            in_reply_to="<orig@providers.example>",
            references=["<orig@providers.example>"],
            from_name="Afterward",
            footer_ref=marker,
        )
    )
    assert sent.thread_id == "thread-7"
    raw = base64.urlsafe_b64decode(transport.sent[0]["raw"].encode())
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    assert parsed["In-Reply-To"] == "<orig@providers.example>"
    assert "<orig@providers.example>" in parsed["References"]
    assert transport.sent[0]["threadId"] == "thread-7"
    assert parsed["Message-ID"] == sent.rfc_message_id
    found = await box.search_sent(FAMILY, marker)
    assert found is not None
    assert found.gmail_id == "m-sent-copy"
    assert marker in found.text
    assert await box.search_sent(FAMILY, "") is None


@pytest.mark.asyncio
async def test_send_without_the_marker_and_unknown_ids_fail_closed():
    transport = Transport()
    box = _box(transport)
    with pytest.raises(FooterMissing):
        await box.send(
            SendRequest(
                mailbox=FAMILY,
                to_addrs=["bereavement@northline.example"],
                subject="Line",
                text="No marker here.",
                footer_ref="AW-1042-9",
            )
        )
    with pytest.raises(MailNotFound):
        await box.get(FAMILY, "missing")
    assert box.token_valid("other@example.com") is False
    assert box.token_valid(FAMILY) is True


def test_google_transport_requests_inbox_history_and_hides_credentials():
    class Gone(Exception):
        def __init__(self) -> None:
            self.resp = type("Response", (), {"status": 404})()

    class Service:
        def __init__(self) -> None:
            self.history_kwargs = None
            self.sent = None

        def users(self):
            return self

        def history(self):
            return self

        def messages(self):
            return self

        def list(self, **kwargs):
            if "startHistoryId" in kwargs:
                self.history_kwargs = kwargs
                error = Gone() if kwargs["startHistoryId"] == "missing" else None
                return _Done({"historyId": "8", "history": []}, error)
            return _Done({"messages": [{"id": "m-1"}], "nextPageToken": None})

        def get(self, **kwargs):
            if kwargs["id"] == "missing":
                return _Done({}, Gone())
            return _Done(_resource(kwargs["id"], "Hello"))

        def send(self, **kwargs):
            self.sent = kwargs["body"]
            raise TimeoutError

        def getProfile(self, **kwargs):
            return _Done({"historyId": "8"})

        def execute(self):
            return {"historyId": "8"}

    class Creds:
        refresh_token = "present"

    service = Service()
    transport = GoogleGmailTransport(Creds())
    transport._service = service
    assert transport.token_valid() is True
    assert "present" not in repr(transport)
    assert transport.history_list("4")["historyId"] == "8"
    assert service.history_kwargs["historyTypes"] == ["messageAdded"]
    assert service.history_kwargs["labelId"] == "INBOX"
    assert service.history_kwargs["startHistoryId"] == "4"
    with pytest.raises(HistoryExpired):
        transport.history_list("missing")
    with pytest.raises(MailNotFound):
        transport.messages_get("missing")
    with pytest.raises(DeliveryUncertain):
        transport.messages_send({"raw": "abc"})
    assert http_status(Gone()) == 404


class _Done:
    def __init__(self, payload, error=None) -> None:
        self.payload = payload
        self.error = error

    def execute(self):
        if self.error is not None:
            raise self.error
        return self.payload
