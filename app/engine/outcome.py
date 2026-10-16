"""Deterministic outcome check and money rule. Model text never decides these."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.models import MoneyItemStatus

VerdictName = Literal["needs_decision", "resolved", "open"]
ConditionKind = Literal["bool", "max_int", "enum"]
ConditionResult = Literal["matched", "violated", "missing"]
ActionResult = Literal["completed", "promised", "acknowledged", "blocked", "refused", "missing"]

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}
_CONSEQUENTIAL = {"close", "transfer", "freeze", "contract_change", "service_change"}


@dataclass(frozen=True)
class FactView:
    """One typed fact already extracted from a commitment."""

    key: str
    value: str
    evidence_quote: str = ""


@dataclass(frozen=True)
class CommitmentView:
    """One commitment ordered by the message that produced it."""

    action: str
    status: str
    interpretation: str
    facts: tuple[FactView, ...]
    negated: bool
    at: datetime
    evidence_quote: str = ""
    scope: str = "this_service"


@dataclass(frozen=True)
class Condition:
    """A plan condition. `value` is the expected bool, the max int, or the enum value."""

    key: str
    type: ConditionKind
    value: str
    allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanView:
    """The approved request the reply is compared with."""

    action: str
    conditions: tuple[Condition, ...]
    completion_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """Side-by-side result. `resolved` is the only completed outcome."""

    verdict: VerdictName
    results: dict[str, str]
    extras: tuple[str, ...]


@dataclass(frozen=True)
class MoneyAssessment:
    """Money status plus whether a dispute may be proposed. Code does not open one."""

    status: MoneyItemStatus
    dispute_proposed: bool
    reason: str


def _as_condition(raw: Condition | dict[str, object]) -> Condition:
    if isinstance(raw, Condition):
        return raw
    allowed = raw.get("allowed") or ()
    kind = raw.get("type") or "bool"
    value = raw.get("value")
    if isinstance(value, bool):
        value = "true" if value else "false"
    return Condition(
        key=str(raw["key"]),
        type=kind,  # type: ignore[arg-type]
        value=str(value),
        allowed=tuple(str(item) for item in allowed),  # type: ignore[union-attr]
    )


def conditions_from(raw: Sequence[Condition | dict[str, object]]) -> tuple[Condition, ...]:
    """Normalise JSON plan conditions into typed checks."""
    return tuple(_as_condition(item) for item in raw)


def latest_per_action(commitments: Sequence[CommitmentView]) -> dict[str, CommitmentView]:
    """The newest commitment for each action wins. Older quoted history is not passed in."""
    chosen: dict[str, CommitmentView] = {}
    for commitment in commitments:
        current = chosen.get(commitment.action)
        if current is None or commitment.at >= current.at:
            chosen[commitment.action] = commitment
    return chosen


def _latest_fact(latest: dict[str, CommitmentView], key: str) -> FactView | None:
    found: FactView | None = None
    found_at: datetime | None = None
    for commitment in latest.values():
        if commitment.interpretation != "clear":
            continue
        for fact in commitment.facts:
            if fact.key == key and (found_at is None or commitment.at >= found_at):
                found = fact
                found_at = commitment.at
    return found


def evaluate(condition: Condition, latest: dict[str, CommitmentView]) -> ConditionResult:
    """Ambiguous commitments contribute nothing, so a missing quote never matches."""
    fact = _latest_fact(latest, condition.key)
    if fact is None:
        return "missing"
    if condition.type == "bool":
        token = fact.value.casefold()
        if token not in _TRUE | _FALSE:
            return "missing"
        expected = condition.value.casefold() in _TRUE
        actual = token in _TRUE
        return "matched" if actual is expected else "violated"
    if condition.type == "max_int":
        digits = re.search(r"-?\d+", fact.value)
        try:
            actual = int(digits.group()) if digits else int(fact.value)
            limit = int(condition.value)
        except ValueError:
            return "missing"
        return "matched" if actual <= limit else "violated"
    allowed = condition.allowed or (condition.value,)
    return "matched" if fact.value in allowed else "violated"


def _contract_limit(plan: PlanView) -> int | None:
    for condition in plan.conditions:
        if condition.key == "contract_months" and condition.type == "max_int":
            try:
                return int(condition.value)
            except ValueError:
                return None
    return None


def _has_condition(plan: PlanView, key: str) -> bool:
    return any(condition.key == key for condition in plan.conditions)


def unauthorised_changes(plan: PlanView, latest: dict[str, CommitmentView]) -> tuple[str, ...]:
    """New contract terms, a different completed action, or a price the plan never allowed."""
    extras: list[str] = []
    limit = _contract_limit(plan)
    for action, commitment in latest.items():
        if commitment.interpretation != "clear":
            continue
        if (
            action != plan.action
            and action in _CONSEQUENTIAL
            and commitment.status == "completed"
            and not commitment.negated
        ):
            extras.append(f"unauthorised_{action}")
        for fact in commitment.facts:
            if fact.key == "contract_months":
                try:
                    months = int(fact.value)
                except ValueError:
                    continue
                ceiling = 0 if limit is None else limit
                if months > ceiling:
                    extras.append("new_contract")
            elif fact.key == "monthly_price" and not _has_condition(plan, "monthly_price"):
                extras.append("price_change")
    return tuple(dict.fromkeys(extras))


def match_action(plan_action: str, latest: dict[str, CommitmentView]) -> ActionResult:
    """Map the latest clear commitment for the planned action. Ambiguous stays missing."""
    commitment = latest.get(plan_action)
    if commitment is None or commitment.interpretation != "clear":
        return "missing"
    if commitment.negated and commitment.status == "completed":
        return "refused"
    status = commitment.status
    if status == "completed":
        return "completed"
    if status == "promised":
        return "promised"
    if status in {"acknowledged", "requested"}:
        return "acknowledged"
    if status in {"blocked", "conditional"}:
        return "blocked"
    if status == "refused":
        return "refused"
    return "missing"


def has_completion_evidence(plan: PlanView, latest: dict[str, CommitmentView]) -> bool:
    """Every declared evidence item must be a clear fact key or a phrase in a verified quote."""
    if not plan.completion_evidence:
        return False
    quotes: list[str] = []
    fact_keys: set[str] = set()
    for commitment in latest.values():
        if commitment.interpretation != "clear":
            continue
        quotes.append(commitment.evidence_quote)
        fact_keys.update(fact.key for fact in commitment.facts)
    blob = "\n".join(quotes).casefold()
    for item in plan.completion_evidence:
        if item in fact_keys or item.casefold() in blob:
            continue
        return False
    return True


def outcome_check(plan: PlanView, commitments: Sequence[CommitmentView]) -> Verdict:
    """Compare a plan with commitment records. Completion needs evidence and every condition."""
    latest = latest_per_action(commitments)
    results: dict[str, str] = {"action": match_action(plan.action, latest)}
    for condition in plan.conditions:
        results[condition.key] = evaluate(condition, latest)
    extras = unauthorised_changes(plan, latest)
    if any(value == "violated" for value in results.values()) or extras:
        return Verdict("needs_decision", results, extras)
    condition_results = [results[condition.key] for condition in plan.conditions]
    if (
        results["action"] == "completed"
        and all(value == "matched" for value in condition_results)
        and has_completion_evidence(plan, latest)
    ):
        return Verdict("resolved", results, ())
    return Verdict("open", results, ())


def assess_money(
    *,
    kind: str,
    service_period_start: date | None = None,
    closure_effective_date: date | None = None,
    date_of_death: date | None = None,
    promised: bool = False,
    issued: bool = False,
    statement_evidence: bool = False,
    balance_owed: bool = False,
) -> MoneyAssessment:
    """Dispute only when the service period starts after closure. A balance is never disputed."""
    del date_of_death  # A charge after death is still needs review until the period is known.
    if balance_owed or kind == "balance":
        return MoneyAssessment(MoneyItemStatus.balance_owed, False, "balance_owed")
    if kind == "refund" or promised:
        if statement_evidence:
            return MoneyAssessment(MoneyItemStatus.received, False, "statement_evidence")
        if issued:
            return MoneyAssessment(
                MoneyItemStatus.issued_awaiting_receipt, False, "issued_without_receipt"
            )
        return MoneyAssessment(MoneyItemStatus.refund_promised, False, "refund_promised")
    if (
        service_period_start is not None
        and closure_effective_date is not None
        and service_period_start > closure_effective_date
    ):
        return MoneyAssessment(MoneyItemStatus.likely_error, True, "service_after_closure")
    return MoneyAssessment(MoneyItemStatus.needs_review, False, "needs_review")
