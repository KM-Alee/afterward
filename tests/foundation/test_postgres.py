"""Exercise real schema isolation and SKIP LOCKED without product table implementations."""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


def test_schema_is_private_to_session(db_connection):
    schema = db_connection.scalar(text("SELECT current_schema()"))
    assert schema.startswith("test_")
    assert db_connection.scalar(text("SELECT version()")).startswith("PostgreSQL")
    db_connection.execute(text("CREATE TABLE session_probe (id integer PRIMARY KEY)"))
    db_connection.execute(text("INSERT INTO session_probe VALUES (1)"))
    assert db_connection.scalar(text("SELECT count(*) FROM session_probe")) == 1


def test_skip_locked_uses_another_connection(db_engine):
    with db_engine.begin() as connection:
        connection.execute(text("CREATE TABLE lock_probe (id integer PRIMARY KEY)"))
        connection.execute(text("INSERT INTO lock_probe VALUES (1), (2)"))
    try:
        with (
            db_engine.connect() as first,
            db_engine.connect() as second,
            first.begin(),
            second.begin(),
        ):
            assert first.scalar(text("SELECT id FROM lock_probe WHERE id = 1 FOR UPDATE")) == 1
            assert second.scalars(
                text("SELECT id FROM lock_probe ORDER BY id FOR UPDATE SKIP LOCKED")
            ).all() == [2]
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("DROP TABLE lock_probe"))
