"""Read the T14 process environment without loading any dotenv or private files."""

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.engine import make_url


class Settings(BaseModel):
    """Validated environment settings; credentials never appear in representations."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    app_env: str = "dev"
    public_base_url: str = ""
    database_url: SecretStr = Field(default=SecretStr(""), repr=False)
    openai_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    stt_model: str = "gpt-transcribe"
    llm_fast_model: str = "gpt-6-luna"
    llm_accurate_model: str = "gpt-6.1-sol"
    tts_model: str = "gpt-4o-mini-tts"
    llm_fast_effort: str = "none"
    llm_accurate_effort: str = "low"
    tts_voice: str = "marin"
    realtime_model: str = "gpt-realtime-2.1"
    realtime_transcribe_model: str = "gpt-live-transcribe"
    realtime_voice: str = "marin"
    agents_tracing: bool = True
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), repr=False)
    telegram_webhook_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    telegram_mode: str = "webhook"
    whatsapp_token: SecretStr = Field(default=SecretStr(""), repr=False)
    whatsapp_app_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    whatsapp_verify_token: SecretStr = Field(default=SecretStr(""), repr=False)
    whatsapp_phone_number_id: str = Field(default="", repr=False)
    google_client_id: SecretStr = Field(default=SecretStr(""), repr=False)
    google_client_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    google_refresh_token_family: SecretStr = Field(default=SecretStr(""), repr=False)
    google_refresh_token_providers: SecretStr = Field(default=SecretStr(""), repr=False)
    family_mailbox: str = Field(default="", repr=False)
    providers_mailbox: str = Field(default="", repr=False)
    vault_key: SecretStr = Field(default=SecretStr(""), repr=False)
    demo_passcode: SecretStr = Field(default=SecretStr(""), repr=False)
    phone_calls_enabled: bool = False
    twilio_account_sid: SecretStr = Field(default=SecretStr(""), repr=False)
    twilio_auth_token: SecretStr = Field(default=SecretStr(""), repr=False)
    twilio_caller_number: str = Field(default="", repr=False)
    fastn_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    fastn_api_host: str = ""
    fastn_workflow_id: str = ""
    poll_seconds: int = Field(default=15, ge=1)
    log_transcripts: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Read only named T14 variables; empty values retain safe defaults."""
        source = os.environ if environ is None else environ
        return cls(
            **{name: source[name.upper()] for name in cls.model_fields if source.get(name.upper())}
        )


def postgres_url(raw: str) -> str:
    """Normalise supported PostgreSQL schemes and reject other database engines."""
    url = make_url(raw)
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("A PostgreSQL URL is required")
    return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
