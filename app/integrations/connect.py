"""Family mailbox connect: Google OAuth web flow, gmail.readonly only.

A family member connects a household inbox, or the deceased's own mailbox using
access they already hold. The deceased's mailbox needs a stated authority, which
is recorded as stated and never verified. The refresh token is encrypted with the
vault cipher and never logged. A connected mailbox is read-only: its send raises.

Operator step: add `<PUBLIC_BASE_URL>/connect/gmail/callback` to the authorised
redirect URIs of the Google OAuth client, and add the gmail.readonly scope to the
consent screen. The web slice mounts the two routes that call these functions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts import SendRequest, SentRecord
from app.discovery.vault import VaultCipher
from app.integrations.google import TOKEN_URI, credentials_from_refresh
from app.mail.errors import MailboxNotConfigured, MailError
from app.mail.gmail import GmailMailbox
from app.models import MailConnection, ProcessedUpdate

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
CALLBACK_PATH = "/connect/gmail/callback"
STATE_TTL_S = 600
ACCOUNT_OF = ("household", "deceased")
STATE_CHANNEL = "gmail_connect"


class ConnectError(MailError):
    """A connect rule failed closed. Messages never carry codes, tokens or addresses."""


class OAuthTransport(Protocol):
    """The two networked calls. Tests inject a fake; the live one is `LiveOAuthTransport`."""

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str, client_id: str, secret: str
    ) -> dict[str, Any]: ...

    def email_for(self, access_token: str) -> str: ...


class LiveOAuthTransport:
    """Token exchange and profile lookup over HTTPS."""

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str, client_id: str, secret: str
    ) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            }
        ).encode()
        request = urllib.request.Request(TOKEN_URI, data=body, method="POST")  # noqa: S310
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read())

    def email_for(self, access_token: str) -> str:
        request = urllib.request.Request(  # noqa: S310
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return str(json.loads(response.read()).get("emailAddress") or "")


class ReadOnlyGmailMailbox(GmailMailbox):
    """A connected mailbox. It can list and read; it can never send."""

    async def send(self, request: SendRequest) -> SentRecord:
        raise MailError("A connected mailbox is read-only")


def redirect_uri(settings: Settings) -> str:
    base = settings.public_base_url.rstrip("/")
    if not base:
        raise ConnectError("PUBLIC_BASE_URL is not configured")
    return f"{base}{CALLBACK_PATH}"


def _key(settings: Settings) -> bytes:
    material = settings.vault_key.get_secret_value()
    if not material:
        raise ConnectError("The vault key is not configured")
    return hashlib.sha256(b"afterward-connect-state|" + material.encode()).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _verifier(settings: Settings, nonce: str) -> str:
    """PKCE verifier derived from the nonce and a server key, so it never travels in the URL."""
    return _b64(hmac.new(_key(settings), b"pkce|" + nonce.encode(), hashlib.sha256).digest())


def _sign(settings: Settings, payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(_key(settings), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _open_state(settings: Settings, state: str) -> dict[str, Any]:
    try:
        body, sig = state.split(".", 1)
        want = _b64(hmac.new(_key(settings), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            raise ConnectError("The connect link is not valid")
        payload = json.loads(_unb64(body))
    except ConnectError:
        raise
    except Exception:
        raise ConnectError("The connect link is not valid") from None
    if not isinstance(payload, dict) or float(payload.get("e", 0)) < time.time():
        raise ConnectError("The connect link has expired")
    return payload


def start_connect(
    settings: Settings,
    *,
    case_id: UUID,
    account_of: str,
    stated_authority: str,
    owner_label: str,
    member_id: UUID | None = None,
) -> str:
    """Build the Google consent URL. Deceased mailboxes need a stated authority."""
    if account_of not in ACCOUNT_OF:
        raise ConnectError("account_of must be household or deceased")
    authority = (stated_authority or "").strip()
    if account_of == "deceased" and not authority:
        raise ConnectError("A deceased person's mailbox needs a stated authority")
    client_id = settings.google_client_id.get_secret_value()
    if not client_id:
        raise ConnectError("Google OAuth is not configured")
    nonce = secrets.token_urlsafe(16)
    state = _sign(
        settings,
        {
            "c": str(case_id),
            "a": account_of,
            "s": authority[:1000],
            "o": (owner_label or "").strip()[:200],
            "m": str(member_id) if member_id else None,
            "n": nonce,
            "e": int(time.time()) + STATE_TTL_S,
        },
    )
    challenge = _b64(hashlib.sha256(_verifier(settings, nonce).encode()).digest())
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri(settings),
            "response_type": "code",
            "scope": READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTH_URI}?{query}"


def finish_connect(
    settings: Settings,
    session: Session,
    *,
    state: str,
    code: str,
    transport: OAuthTransport | None = None,
) -> MailConnection:
    """Verify the state, exchange the code, and store the encrypted refresh token."""
    payload = _open_state(settings, state)
    account_of = str(payload.get("a"))
    authority = str(payload.get("s") or "").strip()
    if account_of not in ACCOUNT_OF or (account_of == "deceased" and not authority):
        raise ConnectError("The connect link is not valid")
    if not code:
        raise ConnectError("No authorisation code was returned")
    nonce = str(payload["n"])
    # Single use: a replayed callback hits the unique (channel, update_id) row.
    try:
        with session.begin_nested():
            session.add(ProcessedUpdate(channel=STATE_CHANNEL, update_id=nonce))
            session.flush()
    except IntegrityError:
        raise ConnectError("The connect link was already used") from None
    live = transport or LiveOAuthTransport()
    try:
        tokens = live.exchange(
            code=code,
            redirect_uri=redirect_uri(settings),
            code_verifier=_verifier(settings, nonce),
            client_id=settings.google_client_id.get_secret_value(),
            secret=settings.google_client_secret.get_secret_value(),
        )
    except Exception:
        raise ConnectError("Google did not accept the authorisation") from None
    scopes = set(str(tokens.get("scope") or "").split())
    if scopes != {READONLY_SCOPE}:
        raise ConnectError("Google returned a scope other than read-only mail")
    refresh = str(tokens.get("refresh_token") or "")
    if not refresh:
        raise ConnectError("Google returned no refresh token; connect again")
    try:
        address = live.email_for(str(tokens.get("access_token") or "")).strip().casefold()
    except Exception:
        raise ConnectError("Could not read the mailbox address") from None
    if not address:
        raise ConnectError("Could not read the mailbox address")
    cipher = VaultCipher(settings.vault_key.get_secret_value())
    ciphertext = cipher.encrypt(refresh.encode())
    case_id = UUID(str(payload["c"]))
    member = UUID(str(payload["m"])) if payload.get("m") else None
    existing = session.scalar(
        select(MailConnection).where(
            MailConnection.case_id == case_id, MailConnection.address == address
        )
    )
    row = existing or MailConnection(case_id=case_id, address=address)
    row.connected_by_member_id = member
    row.owner_label = str(payload.get("o") or "")
    row.account_of = account_of
    row.stated_authority = authority
    row.scope = "readonly"
    row.token_ciphertext = ciphertext
    row.revoked_at = None
    if existing is None:
        session.add(row)
    session.flush()
    return row


def revoke_connection(session: Session, conn: MailConnection) -> None:
    """Stop using the mailbox: the stored token is wiped."""
    from datetime import UTC, datetime

    conn.revoked_at = datetime.now(UTC)
    conn.token_ciphertext = None
    session.flush()


def mailbox_for_connection(settings: Settings, conn: MailConnection) -> GmailMailbox:
    """A read-only Gmail view of a connected mailbox."""
    if conn.revoked_at is not None or not conn.token_ciphertext:
        raise MailboxNotConfigured("That connection has no usable token")
    cipher = VaultCipher(settings.vault_key.get_secret_value())
    token = cipher.decrypt(bytes(conn.token_ciphertext)).decode()
    auth = credentials_from_refresh(
        client_id=settings.google_client_id.get_secret_value(),
        client_secret=settings.google_client_secret.get_secret_value(),
        refresh_token=token,
        scopes=(READONLY_SCOPE,),
    )
    from app.mail.gmail import GoogleGmailTransport

    return ReadOnlyGmailMailbox({conn.address: GoogleGmailTransport(auth.credentials)})
