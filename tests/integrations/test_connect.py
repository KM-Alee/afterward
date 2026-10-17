"""Mailbox connect: state handling, deny paths, token handling and read-only use."""

import asyncio
import logging
import time
import urllib.parse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.contracts import SendRequest
from app.integrations import connect
from app.integrations.connect import (
    READONLY_SCOPE,
    ConnectError,
    finish_connect,
    mailbox_for_connection,
    revoke_connection,
    start_connect,
)
from app.mail.errors import MailboxNotConfigured, MailError
from app.models import MailConnection
from tests.mail.support import malik

REFRESH = "refresh-token-value-for-tests"


def make_settings() -> Settings:
    return Settings(
        public_base_url="https://afterward.example",
        google_client_id=SecretStr("client-id"),
        google_client_secret=SecretStr("client-secret"),
        vault_key=SecretStr(Fernet.generate_key().decode()),
    )


class FakeOAuth:
    def __init__(self, scope: str = READONLY_SCOPE, refresh: str = REFRESH) -> None:
        self.scope, self.refresh, self.calls = scope, refresh, []

    def exchange(self, **kwargs):
        self.calls.append(kwargs)
        return {"scope": self.scope, "refresh_token": self.refresh, "access_token": "at"}

    def email_for(self, access_token: str) -> str:
        return "Aunt.Home@example.com"


def state_of(url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]


def test_auth_url_is_readonly_with_pkce_and_callback():
    settings = make_settings()
    url = start_connect(
        settings, case_id=uuid4(), account_of="household", stated_authority="", owner_label="Aunt"
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["scope"] == [READONLY_SCOPE]
    assert query["redirect_uri"] == ["https://afterward.example/connect/gmail/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in query


def test_deceased_mailbox_needs_stated_authority():
    with pytest.raises(ConnectError):
        start_connect(
            make_settings(),
            case_id=uuid4(),
            account_of="deceased",
            stated_authority="  ",
            owner_label="Dad",
        )
    with pytest.raises(ConnectError):
        start_connect(
            make_settings(),
            case_id=uuid4(),
            account_of="other",
            stated_authority="x",
            owner_label="",
        )


@pytest.mark.db
def test_connect_stores_an_encrypted_token_and_rejects_replay(db_session, caplog):
    settings = make_settings()
    case = malik(db_session)
    url = start_connect(
        settings,
        case_id=case.id,
        account_of="deceased",
        stated_authority="I am his daughter and know his password",
        owner_label="Dad",
    )
    state = state_of(url)
    oauth = FakeOAuth()
    with caplog.at_level(logging.DEBUG):
        conn = finish_connect(settings, db_session, state=state, code="c1", transport=oauth)
    assert conn.address == "aunt.home@example.com"
    assert conn.account_of == "deceased" and conn.scope == "readonly"
    assert conn.stated_authority.startswith("I am his daughter")
    assert REFRESH.encode() not in bytes(conn.token_ciphertext)
    assert oauth.calls[0]["code_verifier"]
    assert REFRESH not in caplog.text and REFRESH not in repr(conn)
    with pytest.raises(ConnectError):
        finish_connect(settings, db_session, state=state, code="c1", transport=oauth)
    box = mailbox_for_connection(settings, conn)
    assert REFRESH not in repr(box)


@pytest.mark.db
def test_tampered_expired_or_broad_scope_is_rejected(db_session, monkeypatch):
    settings = make_settings()
    case = malik(db_session)
    good = state_of(
        start_connect(
            settings, case_id=case.id, account_of="household", stated_authority="", owner_label="A"
        )
    )
    body, sig = good.split(".")
    for bad in (f"{body}x.{sig}", f"{body}.{sig[:-2]}zz", "garbage", ""):
        with pytest.raises(ConnectError):
            finish_connect(settings, db_session, state=bad, code="c", transport=FakeOAuth())
    # Another server key cannot forge a state.
    other = make_settings()
    forged = state_of(
        start_connect(
            other, case_id=case.id, account_of="household", stated_authority="", owner_label="A"
        )
    )
    with pytest.raises(ConnectError):
        finish_connect(settings, db_session, state=forged, code="c", transport=FakeOAuth())
    with pytest.raises(ConnectError):
        finish_connect(
            settings,
            db_session,
            state=good,
            code="c",
            transport=FakeOAuth(scope=READONLY_SCOPE + " https://mail.google.com/"),
        )
    with pytest.raises(ConnectError):
        finish_connect(settings, db_session, state=good, code="c", transport=FakeOAuth(refresh=""))
    real = time.time()
    monkeypatch.setattr(connect.time, "time", lambda: real + 3600)
    with pytest.raises(ConnectError):
        finish_connect(settings, db_session, state=good, code="c", transport=FakeOAuth())
    assert db_session.scalar(select(MailConnection)) is None


@pytest.mark.db
def test_connected_mailbox_cannot_send_and_revoked_one_is_unusable(db_session):
    settings = make_settings()
    case = malik(db_session)
    state = state_of(
        start_connect(
            settings, case_id=case.id, account_of="household", stated_authority="", owner_label="A"
        )
    )
    conn = finish_connect(settings, db_session, state=state, code="c", transport=FakeOAuth())
    box = mailbox_for_connection(settings, conn)
    request = SendRequest(
        mailbox=conn.address, to_addrs=["x@example.com"], subject="s", text="t", footer_ref=""
    )
    with pytest.raises(MailError):
        asyncio.run(box.send(request))
    revoke_connection(db_session, conn)
    assert conn.token_ciphertext is None
    with pytest.raises(MailboxNotConfigured):
        mailbox_for_connection(settings, conn)


def test_deceased_without_authority_in_a_signed_state_is_still_rejected(db_session=None):
    settings = make_settings()
    state = connect._sign(
        settings,
        {"c": str(uuid4()), "a": "deceased", "s": "", "o": "", "m": None, "n": "n", "e": 2**40},
    )
    with pytest.raises(ConnectError):
        finish_connect(settings, None, state=state, code="c", transport=FakeOAuth())  # type: ignore[arg-type]
