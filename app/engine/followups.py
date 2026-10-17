"""The family's answer to a gentle follow-up question. Only a family button calls this."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.errors import EngineError
from app.engine.executors import run_followup
from app.engine.jobs import cancel_job, complete_job
from app.engine.runner import RunContext
from app.models import Decision, DecisionStatus, Event, Job, JobStatus

CHOICES = frozenset({"send", "not_now"})


async def answer_followup(session: Session, decision_id: UUID, choice: str, *, actor: str) -> str:
    """`send` queues the follow-up under the approval it already has; `not_now` cancels it.

    The send still goes through the send_request job and its preflight (approval current,
    recipient approved, mailbox healthy). Returns the reply text for the family.
    """
    if choice not in CHOICES:
        raise EngineError("followup_choice")
    decision = session.get(Decision, decision_id)
    if decision is None or decision.kind != "followup":
        raise EngineError("decision_missing")
    if decision.status is not DecisionStatus.open:
        raise EngineError("decision_closed")
    job = session.get(Job, UUID(str((decision.payload or {}).get("job_id"))))
    if job is None or job.status is not JobStatus.pending:
        decision.status = DecisionStatus.void
        raise EngineError("followup_gone")
    decision.status = DecisionStatus.chosen
    decision.chosen = choice
    if choice == "send":
        await run_followup(session, job, RunContext(settings=None))
        complete_job(job)
        text = "Okay. The follow-up is queued and goes out once the checks pass."
    else:
        cancel_job(job, "family_not_now")
        text = "Okay, no follow-up for now."
    session.add(
        Event(
            case_id=decision.case_id,
            kind="decision.chosen",
            actor=actor,
            payload={"decision_id": str(decision.id), "choice": choice},
        )
    )
    session.flush()
    return text
