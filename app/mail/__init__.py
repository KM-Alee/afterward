"""Mail and calendar integrations."""

from app.mail.gmail import GmailMailbox
from app.mail.inbound import ingest_message, ingest_messages
from app.mail.outbound import execute_followup, execute_send_request
from app.mail.smoke import mail_smoke

__all__ = [
    "GmailMailbox",
    "execute_followup",
    "execute_send_request",
    "ingest_message",
    "ingest_messages",
    "mail_smoke",
]
