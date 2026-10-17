"""Run the 14 proofs through the live reply, job and approval paths. No network."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.schemas import DependencyOut, ReplyOut
from app.ai.verify import strip_quoted_history
from app.config import Settings
from app.contracts import SendRequest
from app.demo.fixtures.proofs import PROOFS
from app.engine.actions import reconcile_action, record_uncertain, reserve_action
from app.engine.dependencies import apply_dependency
from app.engine.jobs import enqueue, lease_due, preflight
from app.engine.outcome import assess_money
from app.engine.pipeline import (
    HeldDocument,
    can_merge,
    check_recipient,
    extraction_messages,
    process_reply,
)
from app.engine.plans import acceptance_allowed, approve, revise_plan
from app.engine.status import finish_summary
from app.fakes.ai import FakeAI
from app.fakes.mailbox import FakeMailbox
from app.models import (
    Account,
    AccountOrigin,
    ApprovalStatus,
    Autopilot,
    Case,
    CaseControl,
    ChannelName,
    DocsStatus,
    Member,
    MemberRole,
    MoneyItemStatus,
    MoneyStatus,
    Ownership,
    ProofRun,
    ProviderProfile,
    ServiceStatus,
)

router = APIRouter()
APPROVED = "bereavement@northline.example"
REF = "4417"


def get_session():
    """Open a short-lived session. The lead mounts this router; tests override the dependency."""
    raw = Settings.from_env().database_url.get_secret_value() or os.environ.get("DATABASE_URL", "")
    if not raw:
        raise HTTPException(status_code=503, detail="database_unavailable")
    from app.db import make_engine

    engine = make_engine(raw)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _case(session: Session, suffix: str) -> tuple[Case, Member, ProviderProfile, Account]:
    case = Case(
        ref=f"AW-proof-{suffix}",
        deceased_name="Yusuf Malik",
        date_of_death=date(2026, 3, 3),
        intent_text="Stop the bills that do not matter, and keep the voicemail.",
        is_demo=True,
        autopilot=Autopilot.steady,
        control=CaseControl.active,
    )
    session.add(case)
    session.flush()
    member = Member(
        case_id=case.id,
        name="Sara Malik",
        role=MemberRole.owner,
        stated_role_text="daughter, as stated",
        channel=ChannelName.web,
        consent={"status": "granted"},
    )
    profile = ProviderProfile(
        name=f"Northline proof {suffix}",
        accepted_channels=["email"],
        required_info=["account reference"],
        required_docs=[{"type": "death_certificate", "form": "photo"}],
        response_window_bd=5,
        completion_evidence=["cancellation_confirmation"],
        approved_recipients=[APPROVED],
        is_demo=True,
    )
    session.add_all([member, profile])
    session.flush()
    account = Account(
        case_id=case.id,
        provider_id=profile.id,
        account_ref=REF,
        service_label="Mobile line ending 4417",
        holder_name="Yusuf Malik",
        origin=AccountOrigin.forwarded,
        origin_evidence="Synthetic proof",
        ownership=Ownership.confirmed,
    )
    session.add(account)
    session.flush()
    return case, member, profile, account


def _plan(session: Session, case: Case, account: Account, spec: dict[str, Any]):
    return revise_plan(
        session,
        case_id=case.id,
        account_id=account.id,
        action=str(spec.get("action") or "close"),
        conditions=list(spec.get("conditions") or []),
        documents=[],
        recipient=APPROVED,
    )


async def _reply_proof(
    session: Session, ai: Any, spec: dict[str, Any], suffix: str
) -> dict[str, object]:
    case, _member, profile, account = _case(session, suffix)
    plan = _plan(session, case, account, spec)
    text = str(spec["text"])
    latest = strip_quoted_history(text)
    recorded = ReplyOut.model_validate(spec["recorded"])
    if hasattr(ai, "register_structured"):  # recorded mode only; a live model is not scripted
        ai.register_structured("reply_reader", ReplyOut, extraction_messages(latest), recorded)
    held = ()
    if spec.get("held_form"):
        held = (HeldDocument(doc_type="death_certificate", form=str(spec["held_form"])),)
    before = list(profile.approved_recipients)
    result = await process_reply(
        session,
        case=case,
        account=account,
        plan=plan,
        raw_text=text,
        from_addr=APPROVED,
        reply_to=None,
        ai=ai,
        account_refs=[account.account_ref],
        approved_recipients=profile.approved_recipients,
        held_documents=held,
        completion_evidence=tuple(spec.get("completion_evidence") or []),
        closure_effective_date=date(2026, 3, 3),
    )
    if list(profile.approved_recipients) != before:
        raise RuntimeError("recipients_changed")
    if result.disclosed:
        raise RuntimeError("disclosed")
    records: dict[str, object] = {"recipient_check": result.recipient_check.value}
    if "expect_verdict" in spec:
        actual = None if result.verdict is None else result.verdict.verdict
        if actual != spec["expect_verdict"]:
            raise RuntimeError("verdict")
        records["verdict"] = actual
        records["results"] = None if result.verdict is None else result.verdict.results
        records["extras"] = None if result.verdict is None else list(result.verdict.extras)
    if "expect_action" in spec:
        action = None if result.verdict is None else result.verdict.results.get("action")
        if action != spec["expect_action"]:
            raise RuntimeError("action")
        records["action"] = action
    if (
        spec.get("expect_verdict") == "open"
        and result.verdict is not None
        and result.verdict.verdict == "resolved"
    ):
        raise RuntimeError("resolved")
    if result.verdict is not None and "expect_condition" in spec:
        key = str(spec["expect_condition"])
        got = result.verdict.results.get(key)
        if got != spec["expect_condition_result"]:
            raise RuntimeError("condition")
    extra = spec.get("expect_extra")
    if result.verdict is not None and extra and extra not in result.verdict.extras:
        raise RuntimeError("extra")
    if "expect_money" in spec:
        if result.money is None or result.money.status.value != spec["expect_money"]:
            raise RuntimeError("money")
        if result.money.status is MoneyItemStatus.received:
            raise RuntimeError("received")
        records["money"] = result.money.status.value
    if "expect_documents" in spec:
        if result.documents is None or result.documents.value != spec["expect_documents"]:
            raise RuntimeError("documents")
        step = result.next_step or {}
        if "certified" not in str(step.get("action") or "").casefold():
            raise RuntimeError("next_step")
        records["documents"] = result.documents.value
    if account.status_service is ServiceStatus.closed and spec.get("expect_verdict") != "resolved":
        raise RuntimeError("marked_closed")
    return records


async def _recipient_proof(
    session: Session, ai: Any, spec: dict[str, Any], suffix: str
) -> dict[str, object]:
    case, _member, profile, account = _case(session, suffix)
    before = list(profile.approved_recipients)
    result = await process_reply(
        session,
        case=case,
        account=account,
        plan=None,
        raw_text=str(spec["text"]),
        from_addr=str(spec.get("from_addr") or APPROVED),
        reply_to=spec.get("reply_to") if isinstance(spec.get("reply_to"), str) else None,
        ai=ai,
        account_refs=[account.account_ref],
        approved_recipients=profile.approved_recipients,
    )
    if result.recipient_check.value != spec["expect_check"]:
        raise RuntimeError("recipient")
    if not result.held or result.disclosed:
        raise RuntimeError("held")
    if list(profile.approved_recipients) != before:
        raise RuntimeError("recipients_changed")
    direct = check_recipient(
        str(spec.get("from_addr") or APPROVED),
        spec.get("reply_to") if isinstance(spec.get("reply_to"), str) else None,
        profile.approved_recipients,
    )
    if direct.value != spec["expect_check"]:
        raise RuntimeError("recipient")
    return {"recipient_check": result.recipient_check.value, "disclosed": False}


def _money_proof() -> dict[str, object]:
    assessment = assess_money(
        kind="charge",
        service_period_start=date(2026, 2, 1),
        closure_effective_date=date(2026, 3, 3),
        date_of_death=date(2026, 3, 3),
    )
    if assessment.dispute_proposed or assessment.status is not MoneyItemStatus.needs_review:
        raise RuntimeError("money")
    return {"money": assessment.status.value, "dispute_proposed": False}


async def _consent_proof(session: Session, suffix: str) -> dict[str, object]:
    case, member, _profile, account = _case(session, suffix)
    apply_dependency(
        session,
        case_id=case.id,
        account=account,
        dependency=DependencyOut(
            kind="memory",
            statement="Keep the voicemail.",
            linked_provider=None,
            linked_number=None,
            evidence_quote="Keep the voicemail.",
        ),
        source_member_id=member.id,
        plan=None,
    )
    plan = revise_plan(
        session,
        case_id=case.id,
        account_id=account.id,
        action="close",
        conditions=[{"key": "voicemail_preserved", "type": "bool", "value": "true"}],
        documents=[],
        recipient=APPROVED,
    )
    approval = approve(
        session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=member.id,
    )
    job = enqueue(
        session,
        case_id=case.id,
        kind="send_request",
        run_at_case_time=datetime.now(UTC) - timedelta(minutes=5),
        idem_key=f"send:{suffix}",
        payload={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "plan_hash": plan.hash,
            "approval_id": str(approval.id),
            "action": "close",
            "outbound": True,
            "reason": {"type": "always"},
        },
    )
    member.consent = {"status": "revoked"}
    session.flush()
    leased = lease_due(session)
    if job.id not in {item.id for item in leased}:
        raise RuntimeError("lease")
    outcome = preflight(session, job)
    if outcome.ok or outcome.reason != "consent_revoked" or job.status.value != "cancelled":
        raise RuntimeError("consent")
    return {"reason": outcome.reason, "status": job.status.value}


async def _reconcile_proof(session: Session, suffix: str) -> dict[str, object]:
    case, _member, _profile, _account = _case(session, suffix)
    mailbox = FakeMailbox()
    action = reserve_action(
        session,
        case_id=case.id,
        kind="email_send",
        idem_key=f"email:{suffix}",
        request={"footer_ref": f"AW-{suffix}"},
    )
    footer = f"Ref AW-{suffix}"
    await mailbox.send(
        SendRequest(
            mailbox="family",
            to_addrs=[APPROVED],
            subject="Northline",
            text=f"Please close the line.\n\n{footer}",
            footer_ref=footer,
        )
    )
    record_uncertain(action)
    found = await mailbox.search_sent("family", footer)
    name = reconcile_action(action, found=found is not None, search_completed=True)
    if name != "reconciled" or len(mailbox.sent) != 1:
        raise RuntimeError("reconcile")
    return {"action": action.status.value, "sends": len(mailbox.sent)}


def _merge_proof(session: Session, suffix: str) -> dict[str, object]:
    case, _member, profile, first = _case(session, suffix)
    second = Account(
        case_id=case.id,
        provider_id=profile.id,
        account_ref="2290",
        service_label="Mobile line ending 2290",
        holder_name="Yusuf Malik",
        origin=AccountOrigin.photo,
        origin_evidence="Synthetic proof",
        ownership=Ownership.confirmed,
    )
    session.add(second)
    session.flush()
    if can_merge(first, second):
        raise RuntimeError("merged")
    return {"accounts": 2, "merged": False}


def _terms_proof(session: Session, suffix: str) -> dict[str, object]:
    case, member, _profile, account = _case(session, suffix)
    apply_dependency(
        session,
        case_id=case.id,
        account=account,
        dependency=DependencyOut(
            kind="access",
            statement="The bank sends codes to this number.",
            linked_provider=None,
            linked_number="0932",
            evidence_quote="The bank sends codes to this number.",
        ),
        source_member_id=member.id,
        plan=None,
    )
    plan = revise_plan(
        session,
        case_id=case.id,
        account_id=account.id,
        action="transfer",
        conditions=[{"key": "number_kept", "type": "bool", "value": "true"}],
        documents=[{"type": "death_certificate", "form": "photo"}],
        recipient=APPROVED,
    )
    approval = approve(
        session,
        plan_id=plan.id,
        version=plan.version,
        plan_hash_value=plan.hash,
        member_id=member.id,
    )
    if not acceptance_allowed(session, approval.id):
        raise RuntimeError("acceptance")
    revise_plan(
        session,
        case_id=case.id,
        account_id=account.id,
        action="transfer",
        conditions=[
            {"key": "number_kept", "type": "bool", "value": "true"},
            {"key": "contract_months", "type": "max_int", "value": "24"},
        ],
        documents=[{"type": "death_certificate", "form": "photo"}],
        recipient=APPROVED,
    )
    session.refresh(approval)
    voided = approval.status is ApprovalStatus.void
    if not voided or acceptance_allowed(session, approval.id):
        raise RuntimeError("void")
    return {"approval": approval.status.value, "acceptance": False}


def _summary_proof(session: Session, suffix: str) -> dict[str, object]:
    case, _member, profile, _account = _case(session, suffix)
    specs = [
        (
            ServiceStatus.closed,
            MoneyStatus.none,
            DocsStatus.none_needed,
            Ownership.confirmed,
            "afterward",
        ),
        (
            ServiceStatus.acknowledged,
            MoneyStatus.refund_promised,
            DocsStatus.none_needed,
            Ownership.confirmed,
            "provider",
        ),
        (
            ServiceStatus.blocked,
            MoneyStatus.none,
            DocsStatus.none_needed,
            Ownership.confirmed,
            "provider",
        ),
        (
            ServiceStatus.active,
            MoneyStatus.none,
            DocsStatus.none_needed,
            Ownership.confirmed,
            "family",
        ),
        (
            ServiceStatus.active,
            MoneyStatus.none,
            DocsStatus.none_needed,
            Ownership.unconfirmed,
            "family",
        ),
    ]
    rows = []
    for index, (service, money, docs, ownership, owner) in enumerate(specs):
        if index == 0:
            account = _account
            account.status_service = service
            account.status_money = money
            account.status_docs = docs
            account.ownership = ownership
            account.next_step = {"owner": owner, "action": "None", "due_date": None}
        else:
            account = Account(
                case_id=case.id,
                provider_id=profile.id,
                account_ref=f"ref-{index}",
                service_label=f"Service {index}",
                origin=AccountOrigin.manual,
                origin_evidence="Synthetic proof",
                ownership=ownership,
                status_service=service,
                status_money=money,
                status_docs=docs,
                next_step={"owner": owner, "action": "Next", "due_date": None},
            )
            session.add(account)
        rows.append((account, True))
    session.flush()
    summary = finish_summary(rows)
    counts = (
        summary.confirmed,
        summary.promised,
        summary.blocked,
        summary.handed_back,
        summary.unconfirmed,
    )
    if counts != (1, 1, 1, 1, 1):
        raise RuntimeError("summary")
    for word in ("confirmed", "promised", "blocked", "handed", "unconfirmed"):
        if word not in summary.text:
            raise RuntimeError("summary_text")
    return {
        "confirmed": summary.confirmed,
        "promised": summary.promised,
        "blocked": summary.blocked,
        "handed_back": summary.handed_back,
        "unconfirmed": summary.unconfirmed,
        "text": summary.text,
    }


RECORDED_LABEL = "recorded model output"
LIVE_LABEL = "live model output"


async def run_proofs_async(
    session: Session, *, ai: Any | None = None, live: bool = False
) -> dict[str, Any]:
    """Execute every proof. A failure is recorded; it is not hidden.

    Recorded mode replays FakeAI outputs and says so. Live mode asks the real model to read
    each reply, so a pass there shows the same code verdict on real model output.
    """
    if live and ai is None:
        from app.ai.client import AgentsSDKClient

        settings = Settings.from_env()
        if not settings.openai_api_key.get_secret_value():
            raise RuntimeError("live proofs need OPENAI_API_KEY configured by the operator")
        ai = AgentsSDKClient(settings)
    model = ai or FakeAI()
    label = LIVE_LABEL if live else RECORDED_LABEL
    token = uuid4().hex[:8]
    results: list[dict[str, object]] = []
    for spec in PROOFS:
        item = dict(spec)
        suffix = f"{item['id']}-{token}"
        try:
            with session.begin_nested():
                kind = str(item["kind"])
                if kind == "reply":
                    records = await _reply_proof(session, model, item, suffix)
                elif kind == "recipient":
                    records = await _recipient_proof(session, model, item, suffix)
                elif kind == "money":
                    records = _money_proof()
                elif kind == "consent":
                    records = await _consent_proof(session, suffix)
                elif kind == "reconcile":
                    records = await _reconcile_proof(session, suffix)
                elif kind == "merge":
                    records = _merge_proof(session, suffix)
                elif kind == "terms":
                    records = _terms_proof(session, suffix)
                elif kind == "summary":
                    records = _summary_proof(session, suffix)
                else:
                    raise RuntimeError("unknown_proof")
            results.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "passed": True,
                    "latency_ms": 0,
                    "records": records,
                }
            )
        except Exception as exc:
            if isinstance(exc, RuntimeError) and len(str(exc)) < 40:
                code = str(exc)
            else:
                code = type(exc).__name__
            results.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "passed": False,
                    "latency_ms": 0,
                    "records": {"error": code},
                }
            )
    passed = sum(1 for item in results if item["passed"])
    payload = {
        "ok": passed == len(PROOFS),
        "passed": passed,
        "failed": len(PROOFS) - passed,
        "model_output": label,
        "results": results,
    }
    session.add(ProofRun(results=payload))
    session.flush()
    return payload


def run_proofs(session: Session, *, ai: Any | None = None, live: bool = False) -> dict[str, Any]:
    """Synchronous entry point for tests and `POST /api/proofs/run` callers outside a loop."""
    import asyncio

    return asyncio.run(run_proofs_async(session, ai=ai, live=live))


def main() -> int:
    """`make proof`: run all proofs against the configured database and print pass/fail."""
    live = os.environ.get("PROOF_LIVE") == "1"
    raw = Settings.from_env().database_url.get_secret_value() or os.environ.get("DATABASE_URL", "")
    if not raw:
        print("proofs: DATABASE_URL is not set")
        return 2
    from app.db import init_db, make_engine

    engine = make_engine(raw)
    try:
        init_db(engine)
        with Session(engine) as session:
            payload = run_proofs(session, live=live)
            session.commit()
    except RuntimeError as exc:
        print(f"proofs: {exc}")
        return 2
    finally:
        engine.dispose()
    print(f"proofs ({payload['model_output']}): {payload['passed']}/{len(PROOFS)} passed")
    for item in payload["results"]:
        mark = "PASS" if item["passed"] else "FAIL"
        extra = "" if item["passed"] else f"  {item['records']}"
        print(f"  {mark} {item['id']:>2} {item['title']}{extra}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


@router.post("/api/proofs/run")
async def run_proofs_route(session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Structured pass/fail for the 14 cases. The lead mounts this router."""
    return await run_proofs_async(session)
