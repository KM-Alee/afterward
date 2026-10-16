"""Gmail mailbox: history polling, MIME fetch, threaded send and Sent search.

Refresh-token credentials are supplied per mailbox. This module does not log
tokens or message bodies. Tests inject a transport and never open a socket.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from email.utils import make_msgid
from typing import Any, Protocol

from app.contracts import MailCursor, MailMessage, MailNotFound, SendRequest, SentRecord
from app.mail.errors import DeliveryUncertain, FooterMissing, HistoryExpired, MailboxNotConfigured
from app.mail.parse import build_raw_message, extract_text, mail_message_from_gmail

RECENT_QUERY = "newer_than:7d"


class GmailTransport(Protocol):
    """Sync Gmail calls for one mailbox. The live transport is the only networked one."""

    def history_list(self, start_history_id: str) -> dict[str, Any]: ...

    def messages_list(self, query: str) -> list[str]: ...

    def messages_get(self, gmail_id: str) -> dict[str, Any]: ...

    def messages_send(self, body: dict[str, Any]) -> dict[str, Any]: ...

    def profile_history_id(self) -> str: ...

    def token_valid(self) -> bool: ...


class GmailMailbox:
    """Family or provider mailbox. `poll` lists recent mail when history has expired."""

    def __init__(self, transports: Mapping[str, GmailTransport]) -> None:
        self._transports = dict(transports)

    def __repr__(self) -> str:
        names = ", ".join(sorted(self._transports))
        return f"GmailMailbox(mailboxes=[{names}])"

    @classmethod
    def from_credentials(cls, credentials_by_mailbox: Mapping[str, object]) -> GmailMailbox:
        """Build live transports. Importing this class does not contact Google."""
        return cls(
            {
                mailbox: GoogleGmailTransport(credentials)
                for mailbox, credentials in credentials_by_mailbox.items()
            }
        )

    def token_valid(self, mailbox: str) -> bool:
        """True when that mailbox has a refresh token. The token is not returned."""
        transport = self._transports.get(mailbox)
        if transport is None:
            return False
        return bool(transport.token_valid())

    async def poll(
        self, mailbox: str, cursor: MailCursor | None
    ) -> tuple[list[MailMessage], MailCursor]:
        transport = self._require(mailbox)
        if cursor is None or cursor.expired or not cursor.history_id:
            return self._recent(mailbox, transport)
        try:
            history = transport.history_list(cursor.history_id)
        except HistoryExpired:
            return self._recent(mailbox, transport)
        ids = _added_ids(history)
        messages = [self._get(mailbox, transport, gmail_id) for gmail_id in ids]
        history_id = str(history.get("historyId") or cursor.history_id)
        return messages, MailCursor(history_id=history_id, expired=False)

    async def get(self, mailbox: str, gmail_id: str) -> MailMessage:
        return self._get(mailbox, self._require(mailbox), gmail_id)

    async def send(self, request: SendRequest) -> SentRecord:
        if request.footer_ref and request.footer_ref not in request.text:
            raise FooterMissing("Send text is missing the visible footer marker")
        transport = self._require(request.mailbox)
        message_id = make_msgid(domain="afterward.example")
        raw = build_raw_message(request, message_id=message_id)
        body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(raw).decode("ascii")}
        if request.thread_id:
            body["threadId"] = request.thread_id
        try:
            response = transport.messages_send(body)
        except TimeoutError:
            raise DeliveryUncertain("Gmail send timed out") from None
        gmail_id = str(response.get("id") or "")
        thread_id = str(response.get("threadId") or request.thread_id or gmail_id)
        return SentRecord(
            mailbox=request.mailbox,
            gmail_id=gmail_id,
            thread_id=thread_id,
            rfc_message_id=message_id,
            footer_ref=request.footer_ref,
            text=request.text,
        )

    async def search_sent(self, mailbox: str, footer_ref: str) -> SentRecord | None:
        if not footer_ref:
            return None
        transport = self._require(mailbox)
        query = f'in:sent "{footer_ref}"'
        for gmail_id in transport.messages_list(query):
            message = self._get(mailbox, transport, gmail_id)
            if footer_ref in message.full_text or footer_ref in message.latest_text:
                extracted = extract_text(message.full_text)
                return SentRecord(
                    mailbox=mailbox,
                    gmail_id=message.gmail_id,
                    thread_id=message.thread_id,
                    rfc_message_id=message.rfc_message_id,
                    footer_ref=footer_ref,
                    text=extracted.latest_text or message.full_text,
                )
        return None

    def _recent(
        self, mailbox: str, transport: GmailTransport
    ) -> tuple[list[MailMessage], MailCursor]:
        messages = [
            self._get(mailbox, transport, gmail_id)
            for gmail_id in transport.messages_list(RECENT_QUERY)
        ]
        history_id = transport.profile_history_id() or None
        return messages, MailCursor(history_id=history_id, expired=False)

    def _get(self, mailbox: str, transport: GmailTransport, gmail_id: str) -> MailMessage:
        resource = transport.messages_get(gmail_id)
        message = mail_message_from_gmail(mailbox, resource)
        if not message.gmail_id:
            message = message.model_copy(update={"gmail_id": gmail_id})
        return message

    def _require(self, mailbox: str) -> GmailTransport:
        try:
            return self._transports[mailbox]
        except KeyError:
            raise MailboxNotConfigured("That mailbox has no configured refresh token") from None


class GoogleGmailTransport:
    """Live Gmail API. Constructing it does not refresh a token or open a socket."""

    def __init__(self, credentials: object) -> None:
        self._credentials = credentials
        self._service: Any = None

    def __repr__(self) -> str:
        return "GoogleGmailTransport(redacted)"

    def token_valid(self) -> bool:
        return bool(getattr(self._credentials, "refresh_token", None))

    def profile_history_id(self) -> str:
        profile = self._api().users().getProfile(userId="me").execute()
        return str(profile.get("historyId") or "")

    def history_list(self, start_history_id: str) -> dict[str, Any]:
        try:
            return (
                self._api()
                .users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                )
                .execute()
            )
        except HistoryExpired:
            raise
        except Exception as exc:
            if http_status(exc) == 404:
                raise HistoryExpired("Gmail history cursor expired") from None
            raise

    def messages_list(self, query: str) -> list[str]:
        ids: list[str] = []
        page: str | None = None
        for _ in range(5):
            kwargs: dict[str, Any] = {"userId": "me", "q": query}
            if page:
                kwargs["pageToken"] = page
            result = self._api().users().messages().list(**kwargs).execute()
            ids.extend(
                str(item["id"])
                for item in result.get("messages", [])
                if isinstance(item, dict) and item.get("id")
            )
            page = result.get("nextPageToken")
            if not page:
                break
        return ids

    def messages_get(self, gmail_id: str) -> dict[str, Any]:
        try:
            fetched = self._api().users().messages().get(userId="me", id=gmail_id, format="full")
            return fetched.execute()
        except MailNotFound:
            raise
        except Exception as exc:
            if http_status(exc) == 404:
                raise MailNotFound("No message for that id") from None
            raise

    def messages_send(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._api().users().messages().send(userId="me", body=body).execute()
        except (TimeoutError, ConnectionError):
            raise DeliveryUncertain("Gmail send timed out") from None

    def _api(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            self._service = build(
                "gmail", "v1", credentials=self._credentials, cache_discovery=False
            )
        return self._service


def http_status(exc: BaseException) -> int | None:
    """Read an HTTP status from a Google client error without reading its body."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "resp", None)
        status = getattr(response, "status", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _added_ids(history: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    records = history.get("history")
    if not isinstance(records, list):
        return ids
    for record in records:
        if not isinstance(record, dict):
            continue
        added = record.get("messagesAdded")
        if not isinstance(added, list):
            continue
        for item in added:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if not isinstance(message, dict) or not message.get("id"):
                continue
            labels = message.get("labelIds")
            if isinstance(labels, list) and labels and "INBOX" not in labels:
                continue
            ids.append(str(message["id"]))
    return ids
