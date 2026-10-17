"""Constraints on the mail connection, update dedupe, snapshot and discovery tables."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Account,
    ConversationSnapshot,
    DiscoverySource,
    MailConnection,
    ProcessedUpdate,
)
from tests.engine.support import make_account, make_case


def _conn(case, **kw):
    base = {
        "case_id": case.id,
        "owner_label": "Sara",
        "account_of": "household",
        "address": "sara@example.test",
        "scope": "readonly",
    }
    return MailConnection(**{**base, **kw})


@pytest.mark.db
def test_household_connection_needs_no_authority(db_session):
    case = make_case(db_session)
    db_session.add(_conn(case))
    db_session.flush()


@pytest.mark.db
@pytest.mark.parametrize("authority", ["", "   "])
def test_deceased_connection_requires_stated_authority(db_session, authority):
    case = make_case(db_session)
    db_session.add(_conn(case, account_of="deceased", stated_authority=authority))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.db
def test_deceased_connection_with_authority_and_bad_owner_kind(db_session):
    case = make_case(db_session)
    db_session.add(_conn(case, account_of="deceased", stated_authority="executor, as stated"))
    db_session.flush()
    db_session.add(_conn(case, account_of="stranger"))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.db
def test_processed_update_is_unique_per_channel(db_session):
    db_session.add(ProcessedUpdate(channel="telegram", update_id="7"))
    db_session.add(ProcessedUpdate(channel="whatsapp", update_id="7"))
    db_session.flush()
    db_session.add(ProcessedUpdate(channel="telegram", update_id="7"))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.db
def test_snapshot_discovery_and_account_columns(db_session):
    case = make_case(db_session)
    db_session.add(ConversationSnapshot(case_id=case.id, state={"step": 2}))
    db_session.add(
        DiscoverySource(case_id=case.id, kind="gmail", started_by="Sara", scope_text="bills")
    )
    account = make_account(db_session, case)
    db_session.flush()
    db_session.refresh(account)
    assert account.track is None and account.evidence_ids == []
    account.track = "close"
    account.evidence_ids = ["doc-1"]
    db_session.flush()
    assert isinstance(account, Account)


@pytest.mark.db
def test_init_db_adds_columns_to_an_old_accounts_table(db_engine):
    from sqlalchemy import text

    from app.db import init_db

    with db_engine.begin() as conn:
        conn.execute(text("ALTER TABLE accounts DROP COLUMN IF EXISTS track"))
        conn.execute(text("ALTER TABLE accounts DROP COLUMN IF EXISTS evidence_ids"))
    init_db(db_engine)
    init_db(db_engine)
    with db_engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='accounts' AND table_schema=current_schema()"
                )
            )
        }
    assert {"track", "evidence_ids"} <= cols
