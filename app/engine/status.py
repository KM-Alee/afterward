"""Four-dimension account status and the code-written finish summary."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import (
    Account,
    DocsStatus,
    MoneyStatus,
    Ownership,
    ServiceStatus,
)

_CONFIRMED_SERVICE = {ServiceStatus.closed, ServiceStatus.transferred, ServiceStatus.frozen}
_SETTLED_MONEY = {MoneyStatus.none, MoneyStatus.received, MoneyStatus.balance_owed}
_SETTLED_DOCS = {DocsStatus.none_needed, DocsStatus.accepted}
_PROMISED_MONEY = {MoneyStatus.refund_promised, MoneyStatus.issued_awaiting_receipt}
_PROMISED_SERVICE = {ServiceStatus.requested, ServiceStatus.acknowledged}


@dataclass(frozen=True)
class FinishSummary:
    """Counts the code computed. `text` is filled from those counts, not from a model."""

    confirmed: int
    promised: int
    blocked: int
    handed_back: int
    unconfirmed: int
    open: int
    text: str


def four_dimensions(
    account: Account,
    *,
    conditions: dict[str, str] | None = None,
) -> dict[str, object]:
    """Service, money, documents and the next step can all be true together."""
    return {
        "service": account.status_service.value,
        "money": account.status_money.value,
        "documents": account.status_docs.value,
        "next_step": dict(account.next_step or {}),
        "conditions": dict(conditions or {}),
    }


def classify_account(account: Account, *, conditions_hold: bool = True) -> str:
    """One honest bucket for the finish question. The snapshot still keeps every dimension."""
    if account.ownership is Ownership.unconfirmed:
        return "unconfirmed"
    if account.status_service is ServiceStatus.blocked:
        return "blocked"
    owner = str((account.next_step or {}).get("owner") or "")
    if owner == "family":
        return "handed_back"
    if account.status_money in _PROMISED_MONEY or account.status_service in _PROMISED_SERVICE:
        return "promised"
    settled = (
        account.status_service in _CONFIRMED_SERVICE
        and account.status_money in _SETTLED_MONEY
        and account.status_docs in _SETTLED_DOCS
        and conditions_hold
    )
    if settled:
        return "confirmed"
    return "open"


def finish_summary(accounts: list[tuple[Account, bool]]) -> FinishSummary:
    """Answer 'did you finish everything?' from stored dimensions. No model is consulted."""
    counts = {
        "confirmed": 0,
        "promised": 0,
        "blocked": 0,
        "handed_back": 0,
        "unconfirmed": 0,
        "open": 0,
    }
    for account, conditions_hold in accounts:
        counts[classify_account(account, conditions_hold=conditions_hold)] += 1
    phrases = [
        f"{counts['confirmed']} confirmed with written evidence.",
        f"{counts['promised']} promised but not yet evidenced.",
        f"{counts['blocked']} blocked on a requirement.",
        f"{counts['handed_back']} handed to you.",
        f"{counts['unconfirmed']} candidate accounts still unconfirmed.",
    ]
    if counts["unconfirmed"] == 1:
        phrases[-1] = "1 candidate account still unconfirmed."
    return FinishSummary(
        confirmed=counts["confirmed"],
        promised=counts["promised"],
        blocked=counts["blocked"],
        handed_back=counts["handed_back"],
        unconfirmed=counts["unconfirmed"],
        open=counts["open"],
        text=" ".join(phrases),
    )
