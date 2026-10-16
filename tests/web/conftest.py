"""Shared client for the desk and call-room pages."""

import pytest
from fastapi.testclient import TestClient

from app.web.factory import create_surface_app

PASSCODE = "fixture-passcode"


@pytest.fixture
def client():
    app = create_surface_app(demo_passcode=PASSCODE)
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient) -> TestClient:
    response = client.post("/access", data={"passcode": PASSCODE}, follow_redirects=False)
    assert response.status_code == 303
    return client


def token_for(mapping: dict[str, object], case_id: object) -> str:
    for token, owner in mapping.items():
        if owner == case_id:
            return token
    raise AssertionError("missing token")
