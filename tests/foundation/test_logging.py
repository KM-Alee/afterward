"""Adversarial checks for logging credentials, arbitrary content and exception data."""

import io
import json
import logging

import pytest

from app.logging import JSONFormatter, RedactionFilter, redact, request_id_context


def emit(*, opt_in=False, message="fixture transcript", extra=None, exception=False):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(opt_in))
    handler.addFilter(RedactionFilter(opt_in))
    logger = logging.getLogger("foundation-test")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        if exception:
            try:
                raise RuntimeError(message)
            except RuntimeError:
                logger.exception(message, extra=extra)
        else:
            logger.info(message, extra=extra)
        return stream.getvalue(), json.loads(stream.getvalue())
    finally:
        handler.close()
        logger.handlers.clear()


def test_text_and_exceptions_absent_by_default():
    value, result = emit(extra={"data": {"body": "fixture email"}}, exception=True)
    assert "fixture transcript" not in value
    assert "fixture email" not in value
    assert "Traceback" not in value
    assert {"request_id", "case_id", "kind"} <= result.keys()


def test_context_and_event_metadata():
    token = request_id_context.set("request-fixture")
    try:
        _, result = emit(extra={"case_id": "case-fixture", "kind": "http.request"})
        assert result["request_id"] == "request-fixture"
        assert result["case_id"] == "case-fixture"
        assert result["kind"] == "http.request"
    finally:
        request_id_context.reset(token)


@pytest.mark.parametrize(
    "value",
    [
        "postgres" + "://fixture:fixture@localhost/db",
        "postgresql+psycopg" + "://fixture:fixture@localhost/db",
        "Bearer " + "fixture-value-only",
        "Authorization: " + "fixture-value-only",
        "password=" + "fixture-value-only",
        "sk-" + "fixturecharacters" * 3,
        "ghp_" + "fixturecharacters" * 3,
        "12345678:" + "fixturecharacters" * 3,
    ],
)
def test_secret_patterns_redact_even_with_opt_in(value):
    output, result = emit(opt_in=True, message=value, extra={"kind": value})
    assert value not in output
    assert "[REDACTED]" in result["message"]
    assert "[REDACTED]" in result["kind"]


def test_nested_sensitive_fields_and_opt_in_content():
    assert redact({"nested": [{"refresh_token": "fixture-value-only"}]}) == {
        "nested": [{"refresh_token": "[REDACTED]"}]
    }
    assert redact({"email_body": "fixture email"})["email_body"] == "[REDACTED]"
    output, result = emit(
        opt_in=True, extra={"data": {"body": "fixture email", "api_key": "fixture"}}
    )
    assert result["message"] == "fixture transcript"
    assert result["data"]["body"] == "fixture email"
    assert result["data"]["api_key"] == "[REDACTED]"
    assert "fixture email" in output
