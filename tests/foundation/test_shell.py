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
            },
            "channels": {"telegram": "webhook", "whatsapp": "disabled"},
            "db_reachable": False,
        }
        assert "fixture-value-only" not in status.text
        for path in ("/", "/docs", "/openapi.json", "/api/cases", "/proofs"):
            assert client.get(path).status_code == 404
    assert {route.path for route in app.routes} == {"/health", "/status"}


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
