"""The local OAuth helper prints a refresh token and does not start a live flow in tests."""

import importlib.util
from pathlib import Path

import pytest

from app.config import Settings
from app.integrations.google import SCOPES, credentials_from_refresh, gmail_mailbox_for
from app.mail.errors import MailboxNotConfigured


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "google_auth.py"
    spec = importlib.util.spec_from_file_location("mail_google_auth_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_prints_the_token_and_writes_nothing(tmp_path, capsys, monkeypatch):
    module = _load()

    class Creds:
        refresh_token = "test-refresh-token"

    class Flow:
        def run_local_server(self, port=0):
            assert port == 0
            return Creds()

    def factory(client_path, scopes):
        assert client_path == "operator-client.json"
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/calendar.events" in scopes
        return Flow()

    monkeypatch.chdir(tmp_path)
    code = module.main(
        ["--client", "operator-client.json", "--mailbox", "providers"],
        flow_factory=factory,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "test-refresh-token"
    assert list(tmp_path.iterdir()) == []
    assert SCOPES == (
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.events",
    )


def test_missing_refresh_token_fails_without_printing_an_access_token(capsys):
    module = _load()

    class Creds:
        refresh_token = None
        token = "access-should-not-print"

    class Flow:
        def run_local_server(self, port=0):
            return Creds()

    code = module.main(
        ["--client", "operator-client.json", "--mailbox", "family"],
        flow_factory=lambda _path, _scopes: Flow(),
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "access-should-not-print" not in captured.err
    with pytest.raises(SystemExit):
        module.main(["--mailbox", "family"], flow_factory=lambda _p, _s: Flow())


def test_unconfigured_mailbox_fails_closed_and_repr_hides_the_token():
    with pytest.raises(MailboxNotConfigured):
        gmail_mailbox_for(Settings.from_env({}), "family")
    auth = credentials_from_refresh(
        client_id="demo-client",
        client_secret="demo-client-secret",
        refresh_token="test-refresh-token",
    )
    assert repr(auth) == "RefreshAuth(redacted)"
    assert "test-refresh-token" not in repr(auth)
