"""The 14 proof cases from AFTERWARD.md §10.4. Results are never invented."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from typing import Any

PROOF_CASES: tuple[dict[str, object], ...] = (
    {
        "n": 1,
        "input": '"We received your request"',
        "required": "Acknowledged, not completed",
        "expected": {"status": "acknowledged", "verdict": "open"},
    },
    {
        "n": 2,
        "input": '"We cannot close until probate arrives"',
        "required": "Blocked on a requirement",
        "expected": {"status": "blocked", "requirement": "probate"},
    },
    {
        "n": 3,
        "input": "April invoice for February service",
        "required": "No automatic dispute; needs review",
        "expected": {"money": "needs_review", "dispute": False},
    },
    {
        "n": 4,
        "input": '"Refund approved" with no statement evidence',
        "required": "Refund promised; outstanding",
        "expected": {"money": "refund_promised"},
    },
    {
        "n": 5,
        "input": '"Transferred, but voicemail will reset"',
        "required": "Condition violated, then a fresh decision",
        "expected": {"voicemail_preserved": "violated", "verdict": "needs_decision"},
    },
    {
        "n": 6,
        "input": '"Completed: new 24-month plan"',
        "required": "Unauthorised change, then a decision",
        "expected": {"unauthorised": ["contract_months=24"], "verdict": "needs_decision"},
    },
    {
        "n": 7,
        "input": "Request for the full will from an unknown address",
        "required": "No disclosure; hold and warn",
        "expected": {"recipient_check": "unapproved", "disclosure": "none"},
    },
    {
        "n": 8,
        "input": "Valid domain but Reply-To points elsewhere",
        "required": "Hold and warn",
        "expected": {"recipient_check": "reply_to_mismatch"},
    },
    {
        "n": 9,
        "input": "Certified copy requested; vault holds a photo",
        "required": "Requirement unmet; next step prepared",
        "expected": {"docs": "requirement_unmet"},
    },
    {
        "n": 10,
        "input": "Owner revokes consent while a send is queued",
        "required": "Execution blocked",
        "expected": {"job": "cancelled", "reason": "consent_revoked"},
    },
    {
        "n": 11,
        "input": "Worker killed right after sending",
        "required": "Delivery uncertain, then reconciled",
        "expected": {"action": "uncertain_then_reconciled"},
    },
    {
        "n": 12,
        "input": "Second account at the same provider",
        "required": "No merge",
        "expected": {"accounts": 2},
    },
    {
        "n": 13,
        "input": "Representative changes terms after the family approved",
        "required": "Approval void before any acceptance is spoken",
        "expected": {"approval": "void", "acceptance_audio": "discarded"},
    },
    {
        "n": 14,
        "input": '"Did you finish everything?"',
        "required": "Confirmed, promised, blocked, handed back, and unconfirmed stay separate",
        "expected": {"summary": "bucketed"},
    },
)


def _import_runner() -> Callable[[], Any] | None:
    """Use Agent A's runner when it is importable. Do not substitute a fake pass."""
    for module_name in ("app.engine.proofs", "app.demo.fixtures.proofs"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        runner = getattr(module, "run_proofs", None)
        if callable(runner):
            return runner
    return None


def not_run_report() -> dict[str, object]:
    """Honest idle state: the 14 cases are listed and none has a result."""
    return {
        "status": "not_run",
        "reason": "The proof runner is not available yet. These 14 cases have not been run.",
        "results": [
            {
                "n": case["n"],
                "input": case["input"],
                "required": case["required"],
                "expected": case["expected"],
                "state": "not_run",
                "extracted": None,
                "latency_ms": None,
            }
            for case in PROOF_CASES
        ],
    }


def _needs_session(runner: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(runner).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        for parameter in parameters
    )


def _page_report(raw: dict[str, object]) -> dict[str, object] | None:
    """Map the engine runner onto the 14 rows the page already shows."""
    results = raw.get("results")
    if not isinstance(results, list) or len(results) != len(PROOF_CASES):
        return None
    rows = []
    for case, item in zip(PROOF_CASES, results, strict=True):
        if not isinstance(item, dict):
            return None
        passed = bool(item.get("passed"))
        rows.append(
            {
                "n": case["n"],
                "input": case["input"],
                "required": case["required"],
                "expected": case["expected"],
                "state": "pass" if passed else "fail",
                "extracted": item.get("records"),
                "latency_ms": item.get("latency_ms"),
            }
        )
    failed = int(raw.get("failed") or 0)
    passed_count = int(raw.get("passed") or 0)
    return {
        "status": "passed" if failed == 0 else "failed",
        "reason": f"{passed_count} passed, {failed} failed.",
        "results": rows,
    }


def _run_with_database() -> dict[str, object] | None:
    from app.config import Settings
    from app.db import make_engine

    raw_url = Settings.from_env().database_url.get_secret_value()
    if not raw_url:
        return None
    from sqlalchemy.orm import Session

    engine = make_engine(raw_url)
    try:
        with Session(engine) as session:
            report = _import_runner()
            if report is None:
                return None
            raw = report(session)
            session.commit()
    except Exception:
        return None
    finally:
        engine.dispose()
    if not isinstance(raw, dict):
        return None
    return _page_report(raw)


def run_proof_panel(*, live: bool = False) -> dict[str, object]:
    """Call the shared runner, or report that nothing was run."""
    if live:
        ran = _run_with_database()
        if ran is not None:
            return ran
    runner = _import_runner()
    if runner is None:
        return not_run_report()
    if _needs_session(runner):
        report = not_run_report()
        report["reason"] = (
            "The proof runner needs a database session. "
            "These 14 cases have not been run from this page."
        )
        return report
    raw = runner()
    if not isinstance(raw, dict):
        report = not_run_report()
        report["reason"] = "The proof runner returned nothing this page can show."
        return report
    results = raw.get("results")
    if not isinstance(results, list) or len(results) != len(PROOF_CASES):
        report = not_run_report()
        report["reason"] = "The proof runner did not return one result for each of the 14 cases."
        return report
    return raw
