"""Decision and approval cards. Recipients come from provider facts, never from model text."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts import Option, validate_options


class RecipientRejected(Exception):
    """A recipient was not on the approved profile list."""


APPROVE = Option(id="approve_plan", label="Approve")
CHANGE = Option(id="change_plan", label="Change")
NOT_NOW = Option(id="not_now", label="Not now")
KEEP_LINE = Option(id="keep_line", label="Keep the line")
CLOSE_LINE = Option(id="close_line", label="Close it")
HOLD_SAFE = Option(id="hold_safe", label="Hold")
SEE_PLAN = Option(id="see_plan", label="See the plan")


@dataclass(frozen=True)
class ApprovalCard:
    """The exact request the family is asked to approve."""

    recipient: str
    account: str
    action: str
    conditions: tuple[str, ...]
    documents: tuple[str, ...]
    consequence: str
    fallback: str
    options: tuple[Option, ...] = (APPROVE, CHANGE, NOT_NOW)

    def text(self) -> str:
        return (
            f"To: {self.recipient}\n"
            f"Account: {self.account}\n"
            f"Request: {self.action}\n"
            f"Conditions: {' · '.join(self.conditions)}\n"
            f"Documents disclosed: {', '.join(self.documents)}\n"
            f"Consequence: {self.consequence}\n"
            f"If a condition can't be met: {self.fallback}"
        )


def build_approval_card(
    *,
    recipient: str,
    account: str,
    action: str,
    conditions: Sequence[str],
    documents: Sequence[str],
    consequence: str,
    fallback: str,
    allowed_recipients: Sequence[str],
) -> ApprovalCard:
    """Refuse any address that the caller did not already allow."""
    if recipient not in allowed_recipients:
        raise RecipientRejected("Recipient is not on the approved profile list")
    options = (APPROVE, CHANGE, NOT_NOW)
    validate_options(options)
    return ApprovalCard(
        recipient=recipient,
        account=account,
        action=action,
        conditions=tuple(conditions),
        documents=tuple(documents),
        consequence=consequence,
        fallback=fallback,
        options=options,
    )


def read_back_decision(text: str) -> tuple[str, tuple[Option, ...]]:
    """Free text that sounds like a decision is repeated as buttons and not applied."""
    if "whatever you think" in text.lower():
        message = (
            "I won't choose a consequential step for you. The safe default is to hold. "
            "I haven't done anything yet."
        )
        options = (HOLD_SAFE, SEE_PLAN, NOT_NOW)
    else:
        message = (
            "I heard a decision in that message. I haven't done it. Please confirm with a button."
        )
        options = (KEEP_LINE, CLOSE_LINE, NOT_NOW)
    validate_options(options)
    return message, options
