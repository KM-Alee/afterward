"""Table shape and database constraints for the revision 1 schema."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SCHEMA_REVISION, init_db
from app.models import Action, ActionStatus, Base, Case, Job, JobStatus

PRODUCT_TABLES = {
    "cases",
    "members",
    "provider_profiles",
    "accounts",
    "dependencies",
    "plans",
    "approvals",
    "documents",
    "messages",
    "commitments",
    "outcome_checks",
    "money_items",
    "deadlines",
    "decisions",
    "jobs",
    "actions",
    "events",
    "latency",
    "proof_runs",
    "desk_snapshots",
}

GLOBAL_TABLES = {"provider_profiles", "proof_runs", "desk_snapshots"}


def test_revision_declares_every_product_table():
    assert set(Base.metadata.tables) == PRODUCT_TABLES
    for name, table in Base.metadata.tables.items():
        assert "created_at" in table.c
        assert "updated_at" in table.c
        if name == "cases" or name in GLOBAL_TABLES:
            assert "case_id" not in table.c
        else:
            assert "case_id" in table.c
    assert "recipient" in Base.metadata.tables["plans"].c
    assert "facts" in Base.metadata.tables["commitments"].c
    assert "quiet_until" in Base.metadata.tables["cases"].c


@pytest.mark.db
def test_boot_migration_records_revision(db_engine):
    init_db(db_engine)
    with db_engine.connect() as connection:
        revision = connection.scalar(text("SELECT revision FROM schema_migrations"))
    assert revision == SCHEMA_REVISION


@pytest.mark.db
def test_demo_clock_offset_and_idempotency(db_session):
    demo = Case(ref="AW-clock", deceased_name="Yusuf Malik", is_demo=True, clock_offset_s=60)
    db_session.add(demo)
    db_session.flush()
    when = datetime(2026, 3, 6, tzinfo=UTC)
    db_session.add(
        Job(
            case_id=demo.id,
            kind="followup",
            run_at_case_time=when,
            idem_key="followup:once",
            status=JobStatus.pending,
        )
    )
    db_session.add(
        Action(
            case_id=demo.id,
            kind="email_send",
            idem_key="email:once",
            status=ActionStatus.pending,
            request={"redacted": True},
        )
    )
    db_session.flush()
    db_session.add(
        Job(
            case_id=demo.id,
            kind="followup",
            run_at_case_time=when,
            idem_key="followup:once",
            status=JobStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    plain = Case(ref="AW-plain", deceased_name="Yusuf Malik", is_demo=False, clock_offset_s=60)
    db_session.add(plain)
    with pytest.raises(IntegrityError):
        db_session.flush()
