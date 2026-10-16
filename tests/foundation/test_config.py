"""Check environment defaults, secret-safe representations and PostgreSQL-only URLs."""

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, postgres_url


def test_defaults_and_empty_environment():
    assert Settings.from_env({}) == Settings.from_env({"POLL_SECONDS": "", "LOG_TRANSCRIPTS": ""})
    assert Settings.from_env({}).log_transcripts is False
    assert Settings.from_env({"LOG_TRANSCRIPTS": "true"}).log_transcripts is True
    assert Settings.from_env({"POLL_SECONDS": "20"}).poll_seconds == 20


def test_all_sensitive_settings_hide_values():
    fields = {
        name.upper(): "fixture-value-only"
        for name, field in Settings.model_fields.items()
        if field.annotation is SecretStr
    }
    settings = Settings.from_env(fields)
    assert fields
    assert "fixture-value-only" not in repr(settings)
    assert "fixture-value-only" not in str(settings)
    assert "fixture-value-only" not in settings.model_dump_json()


def test_validation_errors_hide_input():
    with pytest.raises(ValidationError) as error:
        Settings.from_env({"POLL_SECONDS": "private-input-fixture"})
    assert "private-input-fixture" not in str(error.value)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgres_schemes_normalise(scheme):
    assert postgres_url(scheme + "://localhost/afterward") == (
        "postgresql+psycopg://localhost/afterward"
    )


def test_sqlite_is_rejected():
    with pytest.raises(ValueError, match="PostgreSQL"):
        postgres_url("sqlite://")


def test_realtime_and_phone_defaults_are_safe() -> None:
    settings = Settings.from_env({})
    assert settings.phone_calls_enabled is False
    assert settings.realtime_model == "gpt-realtime-2.1"
    assert settings.agents_tracing is True
    assert Settings.from_env({"PHONE_CALLS_ENABLED": "true"}).phone_calls_enabled is True
