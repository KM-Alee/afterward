"""Google adapters used by mail. Optional fastn MCP is not connected here."""

from app.integrations.google import SCOPES, credentials_from_refresh, gmail_mailbox_for

__all__ = ["SCOPES", "credentials_from_refresh", "gmail_mailbox_for"]
