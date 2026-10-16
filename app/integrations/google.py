"""Refresh-token Google credentials for the family and provider mailboxes.

Tokens stay in memory. This module does not log them or read dotenv files.
fastn MCP is not wired in this slice.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.config import Settings
from app.mail.errors import MailboxNotConfigured

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
SCOPES = (GMAIL_SCOPE, CALENDAR_SCOPE)
TOKEN_URI = "https://oauth2.googleapis.com/token"


class RefreshAuth:
    """Holds Google credentials. Representations never include the token."""

    def __init__(self, credentials: object) -> None:
        self.credentials = credentials

    def __repr__(self) -> str:
        return "RefreshAuth(redacted)"


def credentials_from_refresh(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    scopes: tuple[str, ...] = SCOPES,
) -> RefreshAuth:
    """Build credentials from a refresh token. The token is not copied into logs."""
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(scopes),
    )
    return RefreshAuth(creds)


def gmail_mailbox_for(settings: Settings, role: str):
    """Build a Gmail mailbox for `family` or `providers`. Empty tokens fail closed."""
    from app.mail.gmail import GmailMailbox

    address, token = _role_secret(settings, role)
    if not address or not token:
        raise MailboxNotConfigured("That mailbox has no configured refresh token")
    auth = credentials_from_refresh(
        client_id=settings.google_client_id.get_secret_value(),
        client_secret=settings.google_client_secret.get_secret_value(),
        refresh_token=token,
    )
    return GmailMailbox.from_credentials({address: auth.credentials})


def calendar_transport_for(settings: Settings):
    """Calendar uses the family mailbox refresh token and the calendar scope."""
    from app.mail.calendar import GoogleCalendarTransport

    address, token = _role_secret(settings, "family")
    if not address or not token:
        raise MailboxNotConfigured("The family mailbox has no configured refresh token")
    auth = credentials_from_refresh(
        client_id=settings.google_client_id.get_secret_value(),
        client_secret=settings.google_client_secret.get_secret_value(),
        refresh_token=token,
    )
    return GoogleCalendarTransport(auth.credentials)


def _role_secret(settings: Settings, role: str) -> tuple[str, str]:
    mapping: Mapping[str, tuple[str, str]] = {
        "family": (
            settings.family_mailbox,
            settings.google_refresh_token_family.get_secret_value(),
        ),
        "providers": (
            settings.providers_mailbox,
            settings.google_refresh_token_providers.get_secret_value(),
        ),
    }
    try:
        return mapping[role]
    except KeyError:
        raise MailboxNotConfigured("Unknown mailbox role") from None
