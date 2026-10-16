"""Page client for QA checks of the integrated desk and call room."""

import pytest
from fastapi.testclient import TestClient

from app.web.factory import create_surface_app

PASSCODE = "fixture-passcode"


@pytest.fixture
def client():
    app = create_surface_app(demo_passcode=PASSCODE)
    with TestClient(app) as test_client:
        yield test_client
