"""Reset the seeded demo case in the database. Only the demo case, never a real one."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demo.seed import DEMO_CASE_REF
from app.engine.demo_case import ensure_demo_case
from app.models import Case, MailConnection, ProviderProfile


def reset_demo_rows(session: Session, *, providers_mailbox: str = "") -> None:
    """Delete the demo case (rows cascade) and its demo profiles, then seed it again.

    A mailbox the family connected is carried over, so a reset never forces a new sign-in.
    Raises PermissionError when the row is not a demo case.
    """
    case = session.scalar(select(Case).where(Case.ref == DEMO_CASE_REF))
    if case is None:
        ensure_demo_case(session, providers_mailbox=providers_mailbox)
        return
    if not case.is_demo:
        raise PermissionError("not a demo case")
    kept = [
        {
            column.name: getattr(row, column.name)
            for column in MailConnection.__table__.columns
            if column.name not in {"id", "case_id", "created_at", "updated_at"}
        }
        for row in session.scalars(select(MailConnection).where(MailConnection.case_id == case.id))
    ]
    session.delete(case)
    session.flush()
    for profile in session.scalars(
        select(ProviderProfile).where(ProviderProfile.is_demo.is_(True))
    ):
        session.delete(profile)
    session.flush()
    new_id = ensure_demo_case(session, providers_mailbox=providers_mailbox)
    for values in kept:
        session.add(MailConnection(case_id=new_id, **values))
    session.flush()
