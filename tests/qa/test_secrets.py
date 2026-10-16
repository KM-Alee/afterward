"""Default logs and the status payload do not carry credentials."""

import io
import json
import logging

from fastapi.testclient import TestClient

from app.logging import JSONFormatter, RedactionFilter
from app.main import app


def test_status_payload_has_no_credential_material():
    with TestClient(app) as client:
        payload = client.get("/status").json()
    blob = json.dumps(payload)
    for word in ("postgres", "sk-", "Bearer", "secret", "token", "password"):
        assert word not in blob.casefold()


def test_default_log_line_drops_credentials_and_message_text():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(False))
    handler.addFilter(RedactionFilter(False))
    logger = logging.getLogger("qa-secrets")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    credential = "postgres" + "ql://fixture:fixture@localhost/db"
    try:
        try:
            raise RuntimeError(credential)
        except RuntimeError:
            logger.exception("worker failed", extra={"kind": "job.failed", "note": credential})
    finally:
        handler.close()
        logger.handlers.clear()
    output = stream.getvalue()
    assert credential not in output
    assert "Traceback" not in output
    assert "worker failed" not in output
