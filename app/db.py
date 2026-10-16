"""Engine helpers and the boot migration for contract revision 1."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.config import postgres_url

SCHEMA_REVISION = "contract-rev-1"


def make_engine(url: str) -> Engine:
    """Open PostgreSQL. Other database engines are rejected by `postgres_url`."""
    return create_engine(postgres_url(url), poolclass=NullPool)


def init_db(engine: Engine) -> None:
    """Create product tables and record the boot revision. Safe to repeat."""
    from app.models import Base

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    revision TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO schema_migrations (revision) VALUES (:revision) ON CONFLICT DO NOTHING"
            ),
            {"revision": SCHEMA_REVISION},
        )
