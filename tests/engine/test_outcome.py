"""Outcome check and the money rule, including ambiguous and unauthorised paths."""

from datetime import UTC, date, datetime

from app.engine.outcome import (
    CommitmentView,
    Condition,
    FactView,
    PlanView,
    assess_money,
    outcome_check,
)
from app.models import MoneyItemStatus

AT = datetime(2026, 4, 2, tzinfo=UTC)
EARLIER = datetime(2026, 4, 1, tzinfo=UTC)


def _commitment(
    action,
    status,
    facts=(),
    *,
    interpretation="clear",
    at=AT,
    quote="",
    negated=False,
):
    return CommitmentView(
        action=action,
        status=status,
        interpretation=interpretation,
        facts=tuple(facts),
        negated=negated,
        at=at,
        evidence_quote=quote,
    )


def _fact(key, value, quote="quoted"):
    return FactView(key=key, value=value, evidence_quote=quote)


def test_acknowledgement_is_not_completion():
    verdict = outcome_check(
        PlanView("close", ()),
        [_commitment("close", "acknowledged")],
    )
    assert verdict.verdict == "open"
    assert verdict.results["action"] == "acknowledged"


def test_blocked_requirement_stays_open():
    verdict = outcome_check(PlanView("close", ()), [_commitment("close", "blocked", negated=True)])
    assert verdict.verdict == "open"
    assert verdict.results["action"] == "blocked"


def test_bool_max_int_and_enum_conditions():
    plan = PlanView(
        "transfer",
        (
            Condition("voicemail_preserved", "bool", "true"),
            Condition("contract_months", "max_int", "0"),
            Condition("document_form", "enum", "photo", ("photo", "scan")),
        ),
        completion_evidence=("written confirmation",),
    )
    matched = outcome_check(
        plan,
        [
            _commitment(
                "transfer",
                "completed",
                (
                    _fact("voicemail_preserved", "true"),
                    _fact("contract_months", "0"),
                    _fact("document_form", "photo"),
                ),
                quote="written confirmation",
            )
        ],
    )
    assert matched.verdict == "resolved"
    violated = outcome_check(
        plan,
        [
            _commitment(
                "transfer",
                "completed",
                (
                    _fact("voicemail_preserved", "false"),
                    _fact("contract_months", "24"),
                    _fact("document_form", "original"),
                ),
                quote="written confirmation",
            )
        ],
    )
    assert violated.verdict == "needs_decision"
    assert violated.results["voicemail_preserved"] == "violated"
    assert violated.results["contract_months"] == "violated"
    assert violated.results["document_form"] == "violated"
    assert "new_contract" in violated.extras


def test_missing_condition_and_missing_evidence_do_not_resolve():
    plan = PlanView(
        "close",
        (Condition("number_kept", "bool", "true"),),
        completion_evidence=("cancellation_confirmation",),
    )
    missing = outcome_check(plan, [_commitment("close", "completed")])
    assert missing.results["number_kept"] == "missing"
    assert missing.verdict == "open"
    no_evidence = outcome_check(
        plan,
        [_commitment("close", "completed", (_fact("number_kept", "true"),), quote="done")],
    )
    assert no_evidence.verdict == "open"


def test_latest_message_wins_and_ambiguous_is_missing():
    plan = PlanView("close", (Condition("number_kept", "bool", "true"),), ("done",))
    older = _commitment(
        "close",
        "completed",
        (_fact("number_kept", "true"),),
        at=EARLIER,
        quote="done",
    )
    newer = _commitment(
        "close",
        "completed",
        (_fact("number_kept", "true"),),
        interpretation="ambiguous",
    )
    verdict = outcome_check(plan, [older, newer])
    assert verdict.results["action"] == "missing"
    assert verdict.results["number_kept"] == "missing"
    assert verdict.verdict == "open"


def test_unauthorised_price_and_different_completed_action():
    plan = PlanView("close", (), ("cancellation_confirmation",))
    verdict = outcome_check(
        plan,
        [
            _commitment("close", "acknowledged"),
            _commitment(
                "transfer",
                "completed",
                (_fact("monthly_price", "30"),),
            ),
        ],
    )
    assert verdict.verdict == "needs_decision"
    assert "unauthorised_transfer" in verdict.extras
    assert "price_change" in verdict.extras


def test_money_dispute_only_when_service_starts_after_closure():
    february = assess_money(
        kind="charge",
        service_period_start=date(2026, 2, 1),
        closure_effective_date=date(2026, 3, 3),
        date_of_death=date(2026, 3, 3),
    )
    assert february.status is MoneyItemStatus.needs_review
    assert february.dispute_proposed is False
    same_day = assess_money(
        kind="charge",
        service_period_start=date(2026, 3, 3),
        closure_effective_date=date(2026, 3, 3),
    )
    assert same_day.dispute_proposed is False
    after = assess_money(
        kind="charge",
        service_period_start=date(2026, 4, 1),
        closure_effective_date=date(2026, 3, 3),
    )
    assert after.status is MoneyItemStatus.likely_error
    assert after.dispute_proposed is True
    after_death = assess_money(kind="charge", date_of_death=date(2026, 3, 3))
    assert after_death.status is MoneyItemStatus.needs_review
    assert after_death.dispute_proposed is False


def test_refund_and_balance_statuses():
    promised = assess_money(kind="refund", promised=True)
    issued = assess_money(kind="refund", issued=True)
    received = assess_money(kind="refund", issued=True, statement_evidence=True)
    owed = assess_money(kind="balance", balance_owed=True, service_period_start=date(2026, 4, 1))
    assert promised.status is MoneyItemStatus.refund_promised
    assert issued.status is MoneyItemStatus.issued_awaiting_receipt
    assert received.status is MoneyItemStatus.received
    assert owed.status is MoneyItemStatus.balance_owed
    assert owed.dispute_proposed is False
    assert promised.dispute_proposed is False
