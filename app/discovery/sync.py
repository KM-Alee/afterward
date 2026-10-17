"""Keep the chat's candidate list and the case's account rows as one list.

Accounts are the durable record the desk and onboarding page read. Candidates are what the
Telegram conversation and the discovery agent work on. This runs before and after every turn:

- a candidate the chat found becomes an `unconfirmed` account row (or adds evidence to one);
- a family decision made in either place is copied to the other;
- a decision is never moved back to undecided, and when the two disagree the database wins,
  because the web page writes it directly and audits it.

Ownership only ever comes from a family button on either surface; nothing here invents one.
"""

import hashlib
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.candidates import UNREFERENCED, Candidate
from app.discovery.directory import LOCATORS, track_for
from app.models import (
    Account,
    AccountOrigin,
    DiscoverySource,
    Event,
    Ownership,
    ProviderProfile,
)

logger = logging.getLogger("app.discovery.sync")

NEEDS_CHECK = "needs_check"


def storage_ref(candidate: Candidate) -> str:
    """Unreferenced candidates get a stable per-source key so they never merge."""
    if candidate.account_ref and candidate.account_ref != UNREFERENCED:
        return candidate.account_ref
    basis = "|".join([candidate.provider, *candidate.evidence_ids, candidate.evidence])
    return f"unref-{hashlib.sha256(basis.encode()).hexdigest()[:10]}"


def origin_for(candidate: Candidate) -> tuple[AccountOrigin, str]:
    """Account origin plus the evidence text the desk turns into a label."""
    origin = candidate.origin.casefold()
    evidence = candidate.evidence or candidate.origin
    if origin == "deceased_inbox":
        return AccountOrigin.inbox, f"His inbox: {evidence}"
    if "inbox" in origin:
        return AccountOrigin.inbox, f"Household inbox: {evidence}"
    if "photo" in origin or evidence.startswith("photo:"):
        return AccountOrigin.photo, evidence
    if "forward" in origin:
        return AccountOrigin.forwarded, evidence
    return AccountOrigin.manual, evidence


def _db_choice(account: Account) -> str:
    if account.ownership is Ownership.confirmed:
        return "confirmed"
    if account.ownership is Ownership.not_theirs:
        return "removed"
    if (account.next_step or {}).get("flag") == NEEDS_CHECK:
        return NEEDS_CHECK
    return "unconfirmed"


def _apply_choice(account: Account, choice: str) -> None:
    if choice == "confirmed":
        account.ownership = Ownership.confirmed
    elif choice == "removed":
        account.ownership = Ownership.not_theirs
    elif choice == NEEDS_CHECK:
        account.next_step = {
            **(account.next_step or {}),
            "owner": "family",
            "action": "Check whether this is his",
            "flag": NEEDS_CHECK,
        }


def sync_candidates(session: Session, case_id: UUID, candidates: list[Candidate]) -> int:
    """Two-way reconcile in place. Returns the number of account rows created."""
    accounts = {
        row.account_ref: row
        for row in session.scalars(select(Account).where(Account.case_id == case_id))
    }
    profiles = {
        row.name.casefold(): row
        for row in session.scalars(select(ProviderProfile))
        if getattr(row, "name", None)
    }
    created = 0
    seen: set[str] = set()
    for candidate in candidates:
        ref = storage_ref(candidate)
        seen.add(ref)
        account = accounts.get(ref)
        if account is None:
            origin, evidence = origin_for(candidate)
            profile = profiles.get(candidate.provider.casefold())
            account = Account(
                case_id=case_id,
                provider_id=profile.id if profile is not None else None,
                account_ref=ref,
                service_label=candidate.service_label or candidate.provider or ref,
                holder_name=candidate.holder_name,
                origin=origin,
                origin_evidence=evidence,
                ownership=Ownership.unconfirmed,
                track=candidate.track
                if candidate.track != "unknown"
                else track_for(candidate.provider),
                evidence_ids=list(candidate.evidence_ids),
                next_step={"owner": "family", "action": "Say whose this is"}
                | ({"provider": candidate.provider} if candidate.provider else {}),
            )
            session.add(account)
            accounts[ref] = account
            created += 1
        else:
            merged = list(account.evidence_ids or [])
            for item in candidate.evidence_ids:
                if item not in merged:
                    merged.append(item)
            if merged != list(account.evidence_ids or []):
                account.evidence_ids = merged
            if not account.track:
                account.track = candidate.track
        db_choice = _db_choice(account)
        if db_choice != "unconfirmed":
            if candidate.ownership != db_choice:
                candidate.ownership = db_choice
        elif candidate.ownership in {"confirmed", "removed", NEEDS_CHECK}:
            _apply_choice(account, candidate.ownership)
            session.add(
                Event(
                    case_id=case_id,
                    kind="ownership.set",
                    actor="family (Telegram)",
                    payload={"account_id": str(account.id), "choice": candidate.ownership},
                )
            )
    # Accounts the family added or decided on the web join the chat's list.
    for ref, account in accounts.items():
        if ref in seen or ref.startswith("unref-"):
            continue
        provider = str((account.next_step or {}).get("provider") or "")
        if not provider and account.provider_id is not None:
            profile = session.get(ProviderProfile, account.provider_id)
            provider = profile.name if profile is not None else ""
        candidates.append(
            Candidate(
                account_ref=ref,
                provider=provider or account.service_label,
                service_label=account.service_label,
                holder_name=account.holder_name,
                origin=account.origin.value,
                ownership=_db_choice(account),
                evidence=account.origin_evidence,
                track=account.track or track_for(provider or account.service_label),
                evidence_ids=list(account.evidence_ids or []),
            )
        )
    session.flush()
    if created:
        logger.info("candidates synced", extra={"kind": "discovery.sync", "rows_added": created})
    return created


def sync_locators(session: Session, case_id: UUID, started: set[str], *, by: str) -> None:
    """Locators prepared in chat appear on the page; ones prepared or started there quiet chat.

    Chat only records "prepared": the family says "I started it" on the page, never the agent.
    """
    known = {loc.id: loc for loc in LOCATORS}
    rows = {
        row.kind: row
        for row in session.scalars(
            select(DiscoverySource).where(
                DiscoverySource.case_id == case_id, DiscoverySource.kind.like("locator:%")
            )
        )
    }
    for kind in rows:
        loc_id = kind.split(":", 1)[1]
        if loc_id in known:
            started.add(loc_id)
    for loc_id in sorted(started):
        kind = f"locator:{loc_id}"
        if loc_id in known and kind not in rows:
            session.add(
                DiscoverySource(
                    case_id=case_id,
                    kind=kind,
                    started_by=by,
                    scope_text=known[loc_id].name,
                    status="prepared",
                )
            )
    session.flush()
