"""MIME decoding, latest-text extraction and body hashes.

Quoted history is not returned as the latest text. The full text and the
remainder after stripping are kept only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formataddr, parsedate_to_datetime
from html import unescape

from app.contracts import MailMessage, SendRequest

_ON_WROTE = re.compile(r"^On .+(@|\d).+wrote:\s*$", re.IGNORECASE)
_ORIGINAL = re.compile(r"^-{5,}\s*Original Message\s*-{5,}\s*$", re.IGNORECASE)
_RULE = re.compile(r"^_{8,}\s*$")
_FROM_HEADER = re.compile(r"^From:\s+\S", re.IGNORECASE)
_SENT_HEADER = re.compile(r"^Sent:\s+\S", re.IGNORECASE)
_BLOCK_BREAK = re.compile(r"(?i)<\s*(?:br|/p|/div|/blockquote|blockquote)\b[^>]*>")
_TAG = re.compile(r"<[^>]+>")
_NAMED_ADDRESS = re.compile(r"^\s*(?P<name>.*?)\s*<(?P<addr>[^>]+)>\s*$")


@dataclass(frozen=True)
class ExtractedText:
    """Latest reply text plus hashes of the full body and of that remainder."""

    latest_text: str
    full_sha256: str
    remainder_sha256: str
    quoted_sha256: str


def split_mailbox(value: str) -> tuple[str, str]:
    """Split `Name (demo) <addr>` without treating parentheses as a comment."""
    match = _NAMED_ADDRESS.match(value or "")
    if match:
        return match.group("name").strip().strip('"'), match.group("addr").strip()
    return "", (value or "").strip()


def sha256_text(value: str) -> str:
    """Hex SHA-256 of Unicode text. The same letters always hash the same way."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_text(full_text: str) -> ExtractedText:
    """Strip quoted history and hash both the full body and the remainder."""
    latest, quoted = split_latest(full_text)
    return ExtractedText(
        latest_text=latest,
        full_sha256=sha256_text(full_text),
        remainder_sha256=sha256_text(latest),
        quoted_sha256=sha256_text(quoted),
    )


def split_latest(full_text: str) -> tuple[str, str]:
    """Return the unquoted reply and the quoted history that was removed."""
    normalized = full_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    cut = _marker_index(lines)
    kept: list[str] = []
    removed: list[str] = []
    for index, line in enumerate(lines):
        if index >= cut or line.lstrip().startswith(">"):
            removed.append(line)
        else:
            kept.append(line)
    return "\n".join(kept).strip(), "\n".join(removed).strip()


def html_to_text(value: str) -> str:
    """Turn a simple HTML part into text. Tag structure is not trusted."""
    spaced = _BLOCK_BREAK.sub("\n", value)
    return unescape(_TAG.sub("", spaced)).replace("\xa0", " ")


def plain_from_email(message: EmailMessage) -> str:
    """Prefer text/plain. HTML is used only when a message has no plain part."""
    if message.is_multipart():
        plain: str | None = None
        html: str | None = None
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain" and plain is None:
                plain = str(part.get_content())
            elif content_type == "text/html" and html is None:
                html = str(part.get_content())
        if plain is not None:
            return plain
        if html is not None:
            return html_to_text(html)
        return ""
    if message.get_content_type() == "text/html":
        return html_to_text(str(message.get_content()))
    return str(message.get_content())


def decode_raw_mime(raw: bytes) -> EmailMessage:
    """Parse RFC 2822 bytes. The bytes are data, not instructions."""
    return BytesParser(policy=policy.default).parsebytes(raw)


def build_raw_message(request: SendRequest, *, message_id: str) -> bytes:
    """Build an RFC 2822 message with thread headers and the caller's text."""
    message = EmailMessage()
    message["To"] = ", ".join(request.to_addrs)
    message["Subject"] = request.subject
    if request.from_name:
        message["From"] = formataddr((request.from_name, request.mailbox))
    else:
        message["From"] = request.mailbox
    message["Message-ID"] = message_id
    if request.in_reply_to:
        message["In-Reply-To"] = request.in_reply_to
    if request.references:
        message["References"] = " ".join(request.references)
    message.set_content(request.text)
    return message.as_bytes()


def mail_message_from_raw(
    *,
    mailbox: str,
    gmail_id: str,
    thread_id: str,
    raw: bytes,
    received_at: datetime | None = None,
) -> MailMessage:
    """Decode a raw Gmail message into the shared mail model."""
    parsed = decode_raw_mime(raw)
    full_text = plain_from_email(parsed)
    return _mail_message(
        mailbox=mailbox,
        gmail_id=gmail_id,
        thread_id=thread_id,
        full_text=full_text,
        from_header=str(parsed.get("From") or ""),
        reply_to_header=str(parsed.get("Reply-To") or ""),
        to_header=str(parsed.get("To") or ""),
        subject=str(parsed.get("Subject") or ""),
        rfc_message_id=str(parsed.get("Message-ID") or ""),
        references_header=str(parsed.get("References") or ""),
        date_header=str(parsed.get("Date") or ""),
        internal_date=None,
        received_at=received_at,
    )


def mail_message_from_gmail(mailbox: str, resource: dict[str, object]) -> MailMessage:
    """Decode a Gmail `format=full` resource. The payload is untrusted data."""
    payload = resource.get("payload")
    payload_dict = payload if isinstance(payload, dict) else {}
    headers = _headers(payload_dict.get("headers"))
    full_text = _body_from_payload(payload_dict)
    internal = resource.get("internalDate")
    return _mail_message(
        mailbox=mailbox,
        gmail_id=str(resource.get("id") or ""),
        thread_id=str(resource.get("threadId") or ""),
        full_text=full_text,
        from_header=headers.get("from", ""),
        reply_to_header=headers.get("reply-to", ""),
        to_header=headers.get("to", ""),
        subject=headers.get("subject", ""),
        rfc_message_id=headers.get("message-id", ""),
        references_header=headers.get("references", ""),
        date_header=headers.get("date", ""),
        internal_date=str(internal) if internal else None,
        received_at=None,
    )


def _mail_message(
    *,
    mailbox: str,
    gmail_id: str,
    thread_id: str,
    full_text: str,
    from_header: str,
    reply_to_header: str,
    to_header: str,
    subject: str,
    rfc_message_id: str,
    references_header: str,
    date_header: str,
    internal_date: str | None,
    received_at: datetime | None,
) -> MailMessage:
    extracted = extract_text(full_text)
    from_name, from_addr = split_mailbox(from_header)
    _reply_name, reply_addr = split_mailbox(reply_to_header)
    to_addrs = [address for part in to_header.split(",") if (address := split_mailbox(part)[1])]
    when = received_at or _received_at(date_header, internal_date)
    return MailMessage(
        mailbox=mailbox,
        gmail_id=gmail_id,
        thread_id=thread_id,
        rfc_message_id=rfc_message_id,
        from_addr=from_addr or from_header.strip(),
        from_name=from_name,
        reply_to=reply_addr or None,
        to_addrs=to_addrs,
        subject=subject,
        latest_text=extracted.latest_text,
        full_text=full_text,
        received_at=when,
        references=[item for item in references_header.split() if item],
    )


def _headers(value: object) -> dict[str, str]:
    found: dict[str, str] = {}
    if not isinstance(value, list):
        return found
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").casefold()
        if name:
            found[name] = str(item.get("value") or "")
    return found


def _body_from_payload(payload: dict[str, object]) -> str:
    plain: str | None = None
    html: str | None = None
    for part in _leaf_parts(payload):
        mime = str(part.get("mimeType") or "")
        filename = str(part.get("filename") or "")
        if filename:
            continue
        text = _decode_body(part.get("body"))
        if text is None:
            continue
        if mime == "text/plain" and plain is None:
            plain = text
        elif mime == "text/html" and html is None:
            html = text
    if plain is not None:
        return plain
    if html is not None:
        return html_to_text(html)
    return ""


def _leaf_parts(payload: dict[str, object]) -> list[dict[str, object]]:
    nested = payload.get("parts")
    if isinstance(nested, list) and nested:
        leaves: list[dict[str, object]] = []
        for part in nested:
            if isinstance(part, dict):
                leaves.extend(_leaf_parts(part))
        return leaves
    return [payload]


def _decode_body(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, str) or not data:
        return None
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return raw.decode("utf-8", errors="replace")


def _received_at(date_header: str, internal_date: str | None) -> datetime:
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
        except (TypeError, ValueError, IndexError):
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    if internal_date and internal_date.isdigit():
        return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
    return datetime.now(UTC)


def _marker_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _ON_WROTE.match(stripped) or _wrapped_on(lines, index):
            return index
        if _ORIGINAL.match(stripped) or _RULE.match(stripped):
            return index
        if _outlook_from(lines, index):
            return index
    return len(lines)


def _wrapped_on(lines: list[str], index: int) -> bool:
    first = lines[index].strip()
    if not first.startswith("On "):
        return False
    window = " ".join(item.strip() for item in lines[index : index + 4])
    if "@" not in window:
        return False
    return bool(re.search(r"\bwrote:", window, re.IGNORECASE))


def _outlook_from(lines: list[str], index: int) -> bool:
    if not _FROM_HEADER.match(lines[index].strip()):
        return False
    window = lines[index + 1 : index + 4]
    return any(_SENT_HEADER.match(item.strip()) for item in window)
