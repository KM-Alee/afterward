"""Offline tests and isolated real-Postgres schemas; never load dotenv files."""

import os
import socket
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import postgres_url


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Explicitly permit marked live tests")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        for item in items:
            if item.get_closest_marker("network"):
                item.add_marker(pytest.mark.skip(reason="Live services require --live"))


@pytest.fixture(autouse=True)
def deny_unapproved_network(request, monkeypatch):
    """No sockets by default; DB tests may reach only their configured Postgres host."""
    if request.node.get_closest_marker("network") and request.config.getoption("--live"):
        return
    allowed_host = None
    allowed_port = None
    if request.node.get_closest_marker("db"):
        url = make_url(os.environ.get("DATABASE_URL_TEST", ""))
        allowed_host, allowed_port = url.host, url.port or 5432
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def permitted(address):
        return (
            allowed_host is not None
            and isinstance(address, tuple)
            and address[0]
            in {allowed_host, "127.0.0.1" if allowed_host == "localhost" else allowed_host}
            and address[1] == allowed_port
        )

    def connect(sock, address):
        if not permitted(address):
            raise AssertionError("Network disabled: use app/fakes or explicitly mark a live test")
        return original(sock, address)

    def connect_ex(sock, address):
        if not permitted(address):
            raise AssertionError("Network disabled: use app/fakes or explicitly mark a live test")
        return original_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)


@pytest.fixture(scope="session")
def db_engine():
    """Create one UUID schema per session; concurrent worktrees never share tables."""
    raw = os.environ.get("DATABASE_URL_TEST")
    if not raw:
        pytest.fail("DATABASE_URL_TEST is required for DB tests; run make db-up && make test")
    url = postgres_url(raw)
    admin = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    schema = "test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"},
    )
    try:
        # The lead may supply models.Base later; no product tables exist in this scaffold.
        from app import models

        if hasattr(models, "Base"):
            models.Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def db_connection(db_engine, request):
    if not request.node.get_closest_marker("db"):
        pytest.fail("Tests requesting database fixtures must use @pytest.mark.db")
    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def db_session(db_connection):
    """Allow code to commit inside tests while the outer test transaction rolls back."""
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        yield session
