"""Verify only the infrastructure shell and its non-secret status boundary."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_shell_routes_and_status(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-value-only")
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.json() == {"ok": True}
        assert response.headers["x-request-id"]
        status = client.get("/status")
        assert status.status_code == 200
        assert status.json() == {
            "models": {
                "stt": "gpt-transcribe",
                "fast": "gpt-6-luna",
                "accurate": "gpt-6.1-sol",
                "tts": "gpt-4o-mini-tts",
                "realtime": "gpt-realtime-2.1",
            },
            "channels": {"telegram": "webhook", "whatsapp": "disabled"},
            "mail": "disabled",
            "phone_calls": "disabled",
            "db_reachable": False,
        }
        assert "fixture-value-only" not in status.text
        assert client.get("/").status_code == 200
        assert client.get("/proofs").status_code == 401
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    paths = {getattr(route, "path", "") for route in app.routes}
    assert {"/health", "/status", "/webhooks/telegram"} <= paths


def test_status_does_not_leak_database_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")
    with TestClient(app) as client:
        response = client.get("/status")
        assert response.status_code == 200
        assert response.json()["db_reachable"] is False
        assert "not-a-database-url" not in response.text


@pytest.mark.db
def test_status_reports_real_postgres(monkeypatch, db_engine):
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        assert client.get("/status").json()["db_reachable"] is True
