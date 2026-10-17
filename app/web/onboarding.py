"""Finding accounts: sources the family chooses, candidates they decide on, and connect routes.

Code builds every query, label and suggestion here. Nothing is searched until the family
starts a source, and only the family's buttons change ownership.
"""

from __future__ import annotations

import inspect
import logging
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.candidates import Candidate, set_ownership
from app.discovery.directory import (
    FINANCIAL,
    HANDBACK_STEPS,
    INSURANCE,
    LOCATORS,
    track_for,
)
from app.discovery.household import scope_query
from app.integrations import connect as connect_mod
from app.models import (
    Account,
    AccountOrigin,
    Case,
    ConversationSnapshot,
    DiscoverySource,
    Event,
    MailConnection,
    Member,
    MemberRole,
    Ownership,
)
from app.web.projection import _coverage, _origin_label, _provider_name, resolve_case
from app.web.render import render
from app.web.router import _error, _page, _token_for, get_surface

router = APIRouter()
logger = logging.getLogger(__name__)

CHOICES = {"his": "confirmed", "not_his": "removed", "not_sure": "needs_check"}
TRACK_TEXT = {
    "ordinary": ("neutral", "Can be handled by email"),
    "financial": ("info", "Notify only. Closing may need probate"),
    "insurance_pension": ("info", "Notify only. The claim is yours to file"),
    "handback": ("info", "A person does this step"),
    "unknown": ("unknown", "Not in our directory yet"),
}
BOUNDARY = (
    "We never sign in as him or search government, court or credit records. "
    "We never say we have found everything."
)
HIS_MAIL_WORDING = (
    "Only if you already have a legitimate way in, such as his provider's family process "
    "or a released export. Say what gives you the right. It is recorded as stated, not "
    "verified. We never use his password."
)
_BANNED = ("all ", "every", "complete", "nothing else")


def _family_case(request: Request, token: str):
    surface = get_surface(request)
    case_id = surface.family_tokens.get(token)
    return surface, case_id


def _owner_name(session: Session, case_id: UUID) -> str:
    member = session.scalar(
        select(Member).where(Member.case_id == case_id, Member.role == MemberRole.owner)
    )
    return member.name if member else "Family"


def suggestions(rows: list[dict]) -> list[dict]:
    """Rule-based suggestions from the rows. Each has at most three buttons and never claims
    that the search is finished."""
    out: list[dict] = []
    unconfirmed = [r for r in rows if r["state"] == "proposed"]
    by_provider: dict[str, list[dict]] = {}
    for row in rows:
        by_provider.setdefault(row["provider"], []).append(row)
    for row in unconfirmed:
        if len(by_provider[row["provider"]]) > 1:
            out.append(
                {
                    "text": f"{row['provider']} has more than one account on the list. "
                    f"Whose is {row['label']}?",
                    "why": f"Seen in: {row['sources']}.",
                    "account_id": row["id"],
                    "options": [
                        ("his", "Yusuf's"),
                        ("not_his", "Someone else's"),
                        ("not_sure", "Not sure"),
                    ],
                }
            )
    if any(r["track"] == FINANCIAL for r in rows):
        out.append(
            {
                "text": "A bank statement usually shows direct debits that email does not. "
                "You can send a photo of one in Telegram when you are ready.",
                "why": "A bank account is on the list.",
                "options": [],
            }
        )
    if any(r["track"] == INSURANCE for r in rows):
        out.append(
            {
                "text": "There is an insurance letter on the list. A policy locator can ask "
                "insurers about other policies. They answer the beneficiary directly.",
                "why": "An insurance account is on the list.",
                "options": [],
            }
        )
    clean = []
    for item in out:
        low = f" {item['text'].casefold()} "
        if any(word in low for word in _BANNED):
            continue
        clean.append(item)
    return clean


def _merge_suggestions(first: list[dict], second: list[dict]) -> list[dict]:
    seen = {item.get("account_id") for item in first if item.get("account_id")}
    texts = {item["text"] for item in first}
    rest = [
        item
        for item in second
        if item["text"] not in texts
        and not (item.get("account_id") and item.get("account_id") in seen)
    ]
    return [*first, *rest]


def agent_suggestions(session: Session, case: Case, rows: list[dict]) -> list[dict]:
    """Open suggestions the discovery agent made in Telegram, so both places show one list.

    Account questions become the same ownership buttons as the rule-based ones; the rest are
    shown as text. Questions about accounts already decided are dropped.
    """
    snapshot = session.get(ConversationSnapshot, case.id)
    state = snapshot.state if snapshot is not None else {}
    by_ref = {row["ref"]: row for row in rows}
    out: list[dict] = []
    for item in state.get("suggestions") or []:
        if item.get("status") != "open":
            continue
        text = " ".join(str(item.get("text", "")).split())
        if not text or any(word in f" {text.casefold()} " for word in _BANNED):
            continue
        entry = {"text": text, "why": str(item.get("why", "")), "options": []}
        if item.get("kind") == "which_account":
            row = by_ref.get(str(item.get("target", "")))
            if row is None or row["state"] != "proposed":
                continue
            entry["account_id"] = row["id"]
            entry["options"] = [
                ("his", "Yusuf's"),
                ("not_his", "Someone else's"),
                ("not_sure", "Not sure"),
            ]
        out.append(entry)
    return out


def build_view(session: Session, case: Case) -> dict:
    accounts = list(
        session.scalars(
            select(Account).where(Account.case_id == case.id).order_by(Account.created_at)
        )
    )
    from app.models import ProviderProfile

    profiles = {p.id: p for p in session.scalars(select(ProviderProfile))}
    owner = _owner_name(session, case.id)
    first = owner.split()[0]
    rows = []
    for account in accounts:
        provider = _provider_name(account, profiles)
        flag = (account.next_step or {}).get("flag")
        if account.ownership is Ownership.confirmed:
            state, state_chip = "confirmed", ("holding", "Yusuf's (you confirmed)")
        elif account.ownership is Ownership.not_theirs:
            state, state_chip = "removed", ("void", "Not his")
        elif flag == "needs_check":
            state, state_chip = "needs_check", ("uncertain", "Shared or not sure")
        else:
            state, state_chip = "proposed", ("review", "Unconfirmed")
        track = account.track or track_for(provider)
        rows.append(
            {
                "id": str(account.id),
                "ref": account.account_ref,
                "provider": provider,
                "label": account.service_label,
                "state": state,
                "state_chip": state_chip,
                "sources": " · ".join(
                    x for x in (_origin_label(account, first), account.origin_evidence) if x
                ),
                "track": track,
                "track_chip": TRACK_TEXT.get(track, TRACK_TEXT["unknown"]),
            }
        )
    connections = list(
        session.scalars(
            select(MailConnection)
            .where(MailConnection.case_id == case.id, MailConnection.revoked_at.is_(None))
            .order_by(MailConnection.created_at)
        )
    )
    locator_rows = {
        s.kind: s
        for s in session.scalars(
            select(DiscoverySource).where(
                DiscoverySource.case_id == case.id, DiscoverySource.kind.like("locator:%")
            )
        )
    }
    locators = []
    for loc in LOCATORS:
        source = locator_rows.get(f"locator:{loc.id}")
        step = (
            "none" if source is None else ("started" if source.status == "waiting" else "prepared")
        )
        locators.append({"loc": loc, "step": step, "by": source.started_by if source else ""})
    confirmed_tracks = {r["track"] for r in rows if r["state"] == "confirmed"}
    steps = [
        ("copies", "Certified copies of the death certificate"),
        ("government", "Tell government offices"),
    ]
    handback = [(label, HANDBACK_STEPS[key]) for key, label in steps]
    if FINANCIAL in confirmed_tracks:
        handback.append(("Apply for probate (the grant)", HANDBACK_STEPS["probate"]))
    if INSURANCE in confirmed_tracks:
        handback.append(("Insurance claim", HANDBACK_STEPS["claim"]))
    unconfirmed = [r for r in rows if r["state"] == "proposed"]
    return {
        "case": case,
        "owner": owner,
        "first": first,
        "rows": rows,
        "need": len(unconfirmed),
        "connections": connections,
        "locators": locators,
        "handback": handback,
        "coverage": _coverage(session, case, first, []),
        "suggestions": _merge_suggestions(
            agent_suggestions(session, case, rows), suggestions(rows)
        ),
        "query": scope_query([case.deceased_name], None),
        "his_wording": HIS_MAIL_WORDING,
        "boundary": BOUNDARY,
    }


def _page_response(request: Request, token: str, case_id: UUID, *, status=200, notice="", error=""):
    surface = get_surface(request)
    factory = surface.session_factory
    view = None
    if factory is not None:
        with factory() as session:  # type: ignore[operator]
            case = resolve_case(session, case_id)
            if case is not None:
                view = build_view(session, case)
    return render(
        request,
        "onboarding.html",
        _page(
            request,
            "onboarding",
            token=token,
            view=view,
            notice=notice,
            error=error,
            fit_always=False,
            reveal=True,
        ),
        status_code=status,
    )


@router.get("/family/onboarding")
def onboarding_entry(request: Request):
    """Entry for a signed-in desk user. The family reaches the page through its own link."""
    from app.web.router import _require_desk, signed_in

    if not signed_in(request):
        return _require_desk(request)
    surface = get_surface(request)
    token = _token_for(surface.family_tokens, surface.demo_case_id)
    return RedirectResponse(f"/family/{token}/onboarding", status_code=303)


@router.get("/family/{token}/onboarding")
def onboarding(request: Request, token: str, connected: str = ""):
    surface, case_id = _family_case(request, token)
    if case_id is None:
        return _error(request, "family", 404, "That family link is not valid.")
    notice = "Mailbox connected. Nothing has been searched yet." if connected == "1" else ""
    return _page_response(request, token, case_id, notice=notice)


@router.post("/family/{token}/onboarding/ownership")
async def set_account_ownership(request: Request, token: str):
    surface, case_id = _family_case(request, token)
    if case_id is None:
        return _error(request, "family", 404, "That family link is not valid.")
    form = await request.form()
    choice = CHOICES.get(str(form.get("choice") or ""))
    try:
        account_id = UUID(str(form.get("account_id") or ""))
    except ValueError:
        account_id = None
    if choice is None or account_id is None:
        return _page_response(
            request, token, case_id, status=422, error="That choice is not on the card."
        )
    factory = surface.session_factory
    if factory is None:
        return _page_response(
            request, token, case_id, status=503, error="The database is not set up."
        )
    with factory() as session:  # type: ignore[operator]
        case = resolve_case(session, case_id)
        account = session.get(Account, account_id)
        if case is None or account is None or account.case_id != case.id:
            return _page_response(
                request, token, case_id, status=404, error="That account is not on this case."
            )
        flagged = (account.next_step or {}).get("flag") == "needs_check"
        if account.ownership is not Ownership.unconfirmed or (flagged and choice == "needs_check"):
            return _page_response(
                request, token, case_id, status=409, error="That account was already decided."
            )
        candidate = Candidate(
            account_ref=account.account_ref,
            provider=account.service_label,
            service_label=account.service_label,
            holder_name=account.holder_name,
            origin=account.origin.value,
            ownership="unconfirmed",
        )
        if not set_ownership([candidate], account.account_ref, choice):
            return _page_response(
                request,
                token,
                case_id,
                status=422,
                error="That account has no reference to decide on.",
            )
        if candidate.ownership == "confirmed":
            account.ownership = Ownership.confirmed
        elif candidate.ownership == "removed":
            account.ownership = Ownership.not_theirs
        else:
            account.next_step = {
                "owner": "family",
                "action": "Check whether this is his",
                "flag": "needs_check",
            }
        session.add(
            Event(
                case_id=case.id,
                kind="ownership.set",
                actor=_owner_name(session, case.id),
                payload={"account_id": str(account.id), "choice": candidate.ownership},
            )
        )
        session.commit()
    surface.live.publish(
        case_id, "ownership.set", {"summary": "The family decided on an account"}, actor="family"
    )
    return RedirectResponse(f"/family/{token}/onboarding", status_code=303)


@router.post("/family/{token}/onboarding/locator")
async def locator_step(request: Request, token: str):
    surface, case_id = _family_case(request, token)
    if case_id is None:
        return _error(request, "family", 404, "That family link is not valid.")
    form = await request.form()
    loc_id = str(form.get("locator") or "")
    step = str(form.get("step") or "")
    known = {loc.id: loc for loc in LOCATORS}
    factory = surface.session_factory
    if loc_id not in known or step not in {"prepare", "started"} or factory is None:
        return _page_response(
            request, token, case_id, status=422, error="That step is not available."
        )
    with factory() as session:  # type: ignore[operator]
        case = resolve_case(session, case_id)
        if case is None:
            return _page_response(request, token, case_id, status=404, error="No such case.")
        owner = _owner_name(session, case.id)
        kind = f"locator:{loc_id}"
        row = session.scalar(
            select(DiscoverySource).where(
                DiscoverySource.case_id == case.id, DiscoverySource.kind == kind
            )
        )
        if step == "started" and row is None:
            return _page_response(request, token, case_id, status=409, error="Prepare it first.")
        if row is None:
            row = DiscoverySource(
                case_id=case.id,
                kind=kind,
                started_by=owner,
                scope_text=known[loc_id].name,
                status="prepared",
            )
            session.add(row)
        elif step == "started":
            row.status = "waiting"
            row.started_by = owner
        session.commit()
    return RedirectResponse(f"/family/{token}/onboarding", status_code=303)


@router.post("/family/{token}/onboarding/tell")
async def tell_us(request: Request, token: str):
    surface, case_id = _family_case(request, token)
    if case_id is None:
        return _error(request, "family", 404, "That family link is not valid.")
    form = await request.form()
    text = " ".join(str(form.get("text") or "").split())[:200]
    factory = surface.session_factory
    if not text or factory is None:
        return _page_response(request, token, case_id, status=422, error="Write what he had first.")
    with factory() as session:  # type: ignore[operator]
        case = resolve_case(session, case_id)
        if case is None:
            return _page_response(request, token, case_id, status=404, error="No such case.")
        count = len(
            list(
                session.scalars(
                    select(Account.id).where(
                        Account.case_id == case.id, Account.origin == AccountOrigin.manual
                    )
                )
            )
        )
        session.add(
            Account(
                case_id=case.id,
                account_ref=f"told-{count + 1}",
                service_label=text,
                origin=AccountOrigin.manual,
                origin_evidence=f'You said: "{text}"',
                ownership=Ownership.unconfirmed,
                track=track_for(text),
                next_step={"owner": "family", "action": "Say whose this is"},
            )
        )
        session.commit()
    return RedirectResponse(f"/family/{token}/onboarding", status_code=303)


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


@router.post("/connect/gmail/start")
async def connect_start(request: Request):
    surface = get_surface(request)
    form = await request.form()
    token = str(form.get("token") or "")
    case_id = surface.family_tokens.get(token)
    if case_id is None:
        return _error(request, "family", 404, "That family link is not valid.")
    account_of = str(form.get("account_of") or "")
    authority = " ".join(str(form.get("stated_authority") or "").split())
    if account_of not in {"household", "deceased"}:
        return _page_response(
            request, token, case_id, status=400, error="Choose whose mailbox this is."
        )
    if account_of == "deceased" and not authority:
        return _page_response(
            request,
            token,
            case_id,
            status=400,
            error="Say what gives you the right to open his mailbox before connecting it.",
        )
    settings = getattr(request.app.state, "settings", None)
    factory = surface.session_factory
    start = connect_mod.start_connect
    if settings is None or factory is None:
        return _page_response(
            request,
            token,
            case_id,
            status=503,
            error="Connecting a mailbox needs the database and settings.",
        )
    with factory() as session:  # type: ignore[operator]
        case = resolve_case(session, case_id)
        if case is None:
            return _page_response(request, token, case_id, status=404, error="No such case.")
        db_case_id, owner = case.id, _owner_name(session, case.id)
    try:
        url = await _maybe_await(
            start(
                settings,
                case_id=db_case_id,
                account_of=account_of,
                stated_authority=authority,
                owner_label=owner,
            )
        )
    except (connect_mod.ConnectError, ValueError, PermissionError):
        return _page_response(
            request,
            token,
            case_id,
            status=400,
            error="That connection was not accepted. Google sign-in may not be set up yet.",
        )
    except Exception:
        logger.info("connect start", extra={"kind": "connect.start", "ok": False})
        return _page_response(
            request,
            token,
            case_id,
            status=502,
            error="Google could not be reached. Nothing was connected.",
        )
    if not isinstance(url, str) or not url.startswith("https://"):
        return _page_response(
            request,
            token,
            case_id,
            status=502,
            error="No sign-in link could be made. Nothing was connected.",
        )
    return RedirectResponse(url, status_code=303)


@router.get("/connect/gmail/callback")
async def connect_callback(request: Request, state: str = "", code: str = ""):
    surface = get_surface(request)
    if not state or not code:
        return _error(request, "family", 400, "That connection link is not valid.")
    settings = getattr(request.app.state, "settings", None)
    factory = surface.session_factory
    finish = connect_mod.finish_connect
    if settings is None or factory is None:
        return _error(
            request, "family", 503, "Connecting a mailbox needs the database and settings."
        )
    bad = (ValueError, PermissionError, KeyError, connect_mod.ConnectError)
    try:
        with factory() as session:  # type: ignore[operator]
            result = await _maybe_await(finish(settings, session, state=state, code=code))
            session.commit()
    except bad:
        return _error(request, "family", 400, "That connection link is not valid or has expired.")
    except Exception:
        logger.info("connect finish", extra={"kind": "connect.finish", "ok": False})
        return _error(request, "family", 502, "Google could not be reached. Nothing was connected.")
    db_case = getattr(result, "case_id", None) or (
        result.get("case_id") if isinstance(result, dict) else None
    )
    token = _token_for(surface.family_tokens, surface.demo_case_id)
    if db_case is not None:
        for key, owner in surface.family_tokens.items():
            if owner == db_case:
                token = key
    return RedirectResponse(f"/family/{token}/onboarding?connected=1", status_code=303)
