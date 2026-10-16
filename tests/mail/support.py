"""Shared builders for mail tests. Addresses stay fictional."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demo.seed import seed_malik
from app.models import Account, Action, ActionStatus, Case, Plan, PlanAction, PlanStatus

FAMILY = "family.demo@example.com"
PROVIDERS = "providers.demo@example.com"


def malik(session: Session) -> Case:
    """Insert the demo case with plus-addresses on the providers mailbox."""
    return seed_malik(session, providers_mailbox=PROVIDERS)


def account_by_ref(session: Session, case_id: UUID, account_ref: str) -> Account:
    account = session.scalar(
        select(Account).where(Account.case_id == case_id, Account.account_ref == account_ref)
    )
    assert account is not None
    return account


def approved_plan(session: Session, case: Case, account: Account) -> Plan:
    plan = Plan(
        case_id=case.id,
        account_id=account.id,
        version=1,
        action=PlanAction.transfer,
        conditions=[{"key": "voicemail_preserved", "value": True}],
        documents_to_disclose=[],
        recipient="bereavement@northline.example",
        fallback="Hold and ask the family.",
        status=PlanStatus.approved,
        hash="ab" * 32,
    )
    session.add(plan)
    session.flush()
    return plan


def email_action(
    session: Session,
    case: Case,
    account: Account,
    *,
    idem_key: str,
    action_key: str,
    body: str = "Please transfer the line ending 4417 and keep the voicemail.",
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    status: ActionStatus = ActionStatus.pending,
    attempts: int = 0,
) -> Action:
    request: dict[str, object] = {
        "account_id": str(account.id),
        "to_addrs": ["providers.demo+northline@example.com"],
        "subject": "Line ending 4417",
        "body": body,
        "action_key": action_key,
        "mailbox": FAMILY,
    }
    if thread_id:
        request["thread_id"] = thread_id
    if in_reply_to:
        request["in_reply_to"] = in_reply_to
    action = Action(
        case_id=case.id,
        kind="email_send",
        idem_key=idem_key,
        status=status,
        request=request,
        attempts=attempts,
    )
    session.add(action)
    session.flush()
    return action
