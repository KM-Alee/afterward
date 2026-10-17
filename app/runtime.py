"""Process wiring for the running server: health checks and Telegram updates."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime

from fastapi import Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts import WebhookRejected, WebhookRequest
from app.engine.jobs import complete_job, preflight
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)

_HEALTH_ONLY = """
SELECT j.id FROM jobs j
JOIN cases c ON c.id = j.case_id
WHERE j.kind = 'health_check'
  AND j.status = 'pending'
  AND j.run_at_case_time <= now() + make_interval(secs => c.clock_offset_s)
ORDER BY j.run_at_case_time
FOR UPDATE OF j SKIP LOCKED
LIMIT 5
"""


def run_health_checks(session: Session) -> int:
    """Finish due health-check jobs. Other kinds stay for their own executors."""
    now = datetime.now(UTC)
    finished = 0
    for job_id in session.execute(text(_HEALTH_ONLY)).scalars().all():
        job = session.get(Job, job_id)
        if job is None:
            continue
        job.status = JobStatus.running
        job.lease_until = now
        if preflight(session, job, wall=now).ok:
            complete_job(job)
            finished += 1
    session.flush()
    return finished


_ENGINES: dict[str, object] = {}


def _db_session(settings) -> Session | None:
    """A session on the configured database, or None when the app runs without one."""
    url = settings.database_url.get_secret_value() if settings is not None else ""
    if not url:
        return None
    from app.db import make_engine

    engine = _ENGINES.get(url)
    if engine is None:
        engine = _ENGINES[url] = make_engine(url)
    return Session(engine)


def _conversation(settings: Settings):
    """Build from the case rows when a database is configured; Malik constants otherwise."""
    from app.ai.client import AgentsSDKClient
    from app.conversation.live import build_conversation, connect_url, latest_case_id
    from app.discovery.agent import sdk_runner

    ai = AgentsSDKClient(settings, timeout_s=60, max_retries=1)
    runner = sdk_runner(settings)
    session = _db_session(settings)
    if session is not None:
        try:
            with session:
                case_id = _case_id(session, settings) or latest_case_id(session)
                if case_id is not None:
                    _wire_ai_hooks(ai, settings, session, case_id)
                    built = build_conversation(
                        session, settings, ai, case_id=case_id, runner=runner
                    )
                    session.commit()
                    if built is not None:
                        return built
        except Exception:
            logger.info("conversation build", extra={"kind": "conversation.build", "ok": False})
    return _demo_conversation(ai, runner, connect_url(settings))


def _wire_ai_hooks(ai, settings, session: Session, case_id) -> None:
    """Give the family agent read-only case facts and a proposal sink. Missing -> tools say so."""
    try:
        from app.ai.facts import make_account_facts, make_case_facts, make_proposal_sink
        from app.models import Case

        case = session.get(Case, case_id)
        if case is None:
            return

        def factory() -> Session:
            return _db_session(settings)  # type: ignore[return-value]

        ai.hooks.case_facts = make_case_facts(factory)
        ai.hooks.account_facts = make_account_facts(factory, case.ref)
        ai.hooks.on_proposal = make_proposal_sink(factory, case.ref)
    except Exception:
        logger.info("ai hooks", extra={"kind": "conversation.hooks", "ok": False})


def _case_id(session: Session, settings: Settings):
    try:
        from app.engine.demo_case import ensure_demo_case

        return ensure_demo_case(session, providers_mailbox=settings.providers_mailbox or "")
    except Exception:
        session.rollback()
        return None


def _demo_conversation(ai, runner, url):
    """No database: the fictional Malik constants. Discovery still works on forwards and photos."""
    from app.conversation.demo_malik import ALLOWED_RECIPIENTS, INVITE_TOKEN, NORTHLINE, PROVIDERS
    from app.conversation.session import Conversation, Invite

    return Conversation(
        ai,
        providers=PROVIDERS,
        allowed_recipients=ALLOWED_RECIPIENTS,
        line=NORTHLINE,
        invites={
            INVITE_TOKEN: Invite(
                token=INVITE_TOKEN,
                name="Amina Malik",
                stated_role="his wife; lives in the family home",
            )
        },
        case_date=date(2026, 3, 3),
        discovery_runner=runner,
        discovery=True,
        connect_url=url,
    )


def _telegram(settings: Settings):
    token = settings.telegram_bot_token.get_secret_value()
    secret = settings.telegram_webhook_secret.get_secret_value()
    if not token or not secret:
        return None
    from app.channels.telegram import TelegramChannel
    from app.channels.transport import HttpxTransport

    return TelegramChannel(
        token=token,
        webhook_secret=secret,
        mode=settings.telegram_mode,
        transport=HttpxTransport(),
    )


def _cipher(settings: Settings):
    key = settings.vault_key.get_secret_value()
    if not key:
        return None
    from app.discovery.vault import VaultCipher

    return VaultCipher(key)


async def replies_for(conversation, channel, event, *, cipher) -> list:
    """Turn one verified update into outbound messages. Media is fetched here."""
    if not event.sender:
        return []
    kind = event.kind.value
    if kind == "button" and event.button_id:
        return await conversation.handle_button(event.sender, event.button_id)
    if kind == "text":
        return await conversation.handle_text(event.sender, event.text or "")
    if kind == "voice" and event.media_ref:
        data, _mime = await channel.fetch_media(event.media_ref)
        return await conversation.handle_voice(event.sender, data)
    if kind in {"photo", "document"} and event.media_ref:
        return await _media_replies(conversation, channel, event, cipher=cipher)
    return []


async def _media_replies(conversation, channel, event, *, cipher) -> list:
    from app.conversation.session import Outbound

    data, mime = await channel.fetch_media(event.media_ref)
    if not mime.startswith("image/"):
        return [
            Outbound(
                event.sender,
                "I can read a photo of a bill or a letter. That file is not a picture, "
                "so I have not stored it.",
            )
        ]
    if cipher is None:
        return [
            Outbound(
                event.sender,
                "I can see that picture, but the document key is not set, so I have not stored it.",
            )
        ]
    label = event.text or "photo from the family"
    item = await conversation.ingest_picture(
        image=data,
        mime=mime,
        label=label,
        evidence=f"photo:{conversation.state.photos_ingested + 1}",
        cipher=cipher,
    )
    replies = [Outbound(event.sender, "I saved that picture with the case documents.")]
    replies += await conversation.photo_discovery(
        event.sender, label, doc_type=item.doc_type, image=data, mime=mime
    )
    return replies


async def after_turn(app, conversation, sender: str, replies: list) -> list:
    """Continue the story the desk shows: ask the household, mirror the turn, queue on approval."""
    from app.conversation.session import Outbound
    from app.story import mark_request_sent, reflect_turn

    kinds = [reply.kind for reply in replies]
    if "invite_joined" in kinds:
        asked = conversation.ask_dependency(sender)
        replies = [*replies, *asked]
        kinds += [reply.kind for reply in asked]
    surface = getattr(app.state, "surface", None)
    if surface is not None:
        reflect_turn(surface, conversation, kinds)
    if "approval_recorded" not in kinds or conversation.state.approval is None:
        return replies
    settings = getattr(app.state, "settings", None)
    queued = _queue_send(settings, conversation, sender)
    if queued is False:
        return [
            *replies,
            Outbound(
                sender,
                "Approved, but I couldn't tie it to the saved plan, so nothing was queued or "
                "sent. Ask me to review the plan again.",
                kind="request_not_queued",
            ),
        ]
    if queued is True:
        if surface is not None:
            from app.story import add_event, publish

            note = "Sara approved the plan on Telegram. The request is queued to send once."
            add_event(surface, note, evidence="family", tone="family")
            publish(surface, "request.queued", note, "family")
        return [
            *replies,
            Outbound(
                sender,
                "Queued. It goes out once, under this approval, to the address on the provider "
                "profile. I'll compare their reply with your conditions before anything is "
                "marked done.",
                kind="request_queued",
            ),
        ]
    if surface is None:
        return replies
    text = await mark_request_sent(surface, settings, conversation.state.approval)
    return [*replies, Outbound(sender, text, kind="request_sent")]


def _queue_send(settings, conversation, sender: str) -> bool | None:
    """True when a send_request job was queued, False when it could not be, None without a DB."""
    from app.conversation.live import enqueue_send

    if getattr(conversation, "case_id", None) is None:
        return None
    session = _db_session(settings)
    if session is None:
        return None
    try:
        with session:
            job_id = enqueue_send(session, conversation, sender)
            session.commit()
            return job_id is not None
    except Exception:
        logger.info("send queue", extra={"kind": "job.enqueue", "ok": False})
        return False


async def _followup_button(settings, conversation, event) -> list | None:
    """`fu:<decision>:<choice>` answers the job runner's follow-up question. None if not one."""
    button = getattr(event, "button_id", None) or ""
    if not button.startswith("fu:") or not event.sender:
        return None
    from uuid import UUID

    from app.conversation.session import Outbound
    from app.engine.errors import EngineError
    from app.engine.followups import answer_followup

    member = conversation.state.members.get(event.sender)
    if member is None:
        return [Outbound(event.sender, "Only people on this case can answer that.")]
    parts = button.split(":")
    session = _db_session(settings)
    if len(parts) != 3 or session is None:
        return [Outbound(event.sender, "I don't have that button on the current card.")]
    try:
        with session:
            text = await answer_followup(session, UUID(parts[1]), parts[2], actor=member.name)
            session.commit()
    except (EngineError, ValueError):
        text = "That question was already answered or has expired. Nothing was sent."
    return [Outbound(event.sender, text, kind="followup_answer")]


def _point_connect_link(app, settings, conversation) -> None:
    """Send the family to their own Finding accounts page, where connecting is a form.

    The connect start route is POST-only (it carries the stated authority), so a bare link to
    it would fail; the family page holds both forms.
    """
    base = str(getattr(settings, "public_base_url", "") or "").rstrip("/")
    surface = getattr(app.state, "surface", None)
    if not base or surface is None:
        return
    token = next(
        (key for key, case in surface.family_tokens.items() if case == surface.demo_case_id),
        None,
    )
    if token:
        conversation.connect_url = f"{base}/family/{token}/onboarding#src-household"


def _sync_candidates(settings, conversation) -> None:
    """Pull web decisions and accounts into the chat before a turn."""
    from app.discovery.sync import sync_candidates

    session = _db_session(settings)
    case_id = getattr(conversation, "case_id", None)
    if session is None or case_id is None:
        return
    try:
        with session:
            sync_candidates(session, case_id, conversation.state.candidates)
            _sync_locators(session, conversation)
            session.commit()
    except Exception:
        logger.info("candidate sync", extra={"kind": "discovery.sync", "ok": False})


def _sync_locators(session, conversation) -> None:
    from app.discovery.sync import sync_locators

    tools = getattr(conversation, "tools", None)
    if tools is None:
        return
    owner = conversation.state.members.get(conversation.state.owner_sender or "")
    sync_locators(
        session, conversation.case_id, tools.locators_started, by=owner.name if owner else "Family"
    )


def _save_state(settings, conversation) -> None:
    from app.conversation.live import save_state
    from app.discovery.sync import sync_candidates

    session = _db_session(settings)
    if session is None or getattr(conversation, "case_id", None) is None:
        return
    try:
        with session:
            sync_candidates(session, conversation.case_id, conversation.state.candidates)
            _sync_locators(session, conversation)
            save_state(session, conversation)
            session.commit()
    except Exception:
        logger.info("snapshot save", extra={"kind": "conversation.snapshot", "ok": False})


def _claim_update(settings, update_id: int) -> bool | None:
    """True if new, False if a retry, None when there is no database to ask."""
    from app.conversation.live import claim_update

    session = _db_session(settings)
    if session is None:
        return None
    try:
        with session:
            fresh = claim_update(session, update_id)
            session.commit()
            return fresh
    except Exception:
        logger.info("update claim", extra={"kind": "channel.dedupe", "ok": False})
        return None


def _refresh_scan(settings, conversation) -> None:
    from app.conversation.live import refresh_scan

    session = _db_session(settings)
    if session is None:
        return
    try:
        with session:
            refresh_scan(session, settings, conversation)
    except Exception:
        logger.info("scan refresh", extra={"kind": "discovery.scan", "ok": False})


async def notify_owner(app, text: str, *, buttons: list[tuple[str, str]] | None = None) -> bool:
    """Tell the case owner in Telegram, optionally with buttons. No-op without a chat."""
    conversation = getattr(app.state, "conversation", None)
    channel = getattr(app.state, "telegram_channel", None)
    owner = getattr(getattr(conversation, "state", None), "owner_sender", None)
    if conversation is None or channel is None or not owner:
        return False
    from app.contracts import Option
    from app.conversation.session import Outbound

    options = [Option(id=key, label=label) for key, label in buttons or []] or None
    await _deliver(channel, Outbound(owner, text, options=options))
    return True


async def _deliver(channel, reply) -> None:
    from app.channels.errors import ChannelCallError

    try:
        if reply.options:
            await channel.send_buttons(reply.to, reply.text, list(reply.options))
        else:
            await channel.send_text(reply.to, reply.text)
    except ChannelCallError:
        logger.info("telegram send", extra={"kind": "channel.send", "ok": False})


async def handle_telegram(request: Request) -> Response:
    """Verify a Telegram update and answer it. A bad secret produces no events."""
    settings: Settings = request.app.state.settings
    channel = getattr(request.app.state, "telegram_channel", None)
    if channel is None:
        channel = _telegram(settings)
        if channel is None:
            return Response(status_code=404)
        request.app.state.telegram_channel = channel
    body = await request.body()
    try:
        events = channel.parse_webhook(
            WebhookRequest(body=body, headers=dict(request.headers), query={})
        )
    except WebhookRejected:
        return Response(status_code=401)
    update_id = _update_id(body)
    if update_id is not None:
        fresh = _claim_update(settings, update_id)
        if fresh is None:  # no database: remember in memory for this process
            seen = getattr(request.app.state, "telegram_updates", None)
            if seen is None:
                seen = set()
                request.app.state.telegram_updates = seen
            fresh = update_id not in seen
            seen.add(update_id)
        if not fresh:
            return Response(status_code=200)
    if not settings.openai_api_key.get_secret_value() or not events:
        return Response(status_code=200)
    conversation = getattr(request.app.state, "conversation", None)
    if conversation is None:
        conversation = _conversation(settings)
        request.app.state.conversation = conversation
    _point_connect_link(request.app, settings, conversation)
    lock = getattr(request.app.state, "conversation_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.conversation_lock = lock
    cipher = _cipher(settings)
    async with lock:
        _refresh_scan(settings, conversation)
        _sync_candidates(settings, conversation)
        for event in events:
            try:
                replies = await _followup_button(settings, conversation, event)
                if replies is None:
                    replies = await replies_for(conversation, channel, event, cipher=cipher)
                replies = await after_turn(request.app, conversation, event.sender, replies)
            except Exception:
                logger.info("telegram turn", extra={"kind": "channel.turn", "ok": False})
                continue
            _save_state(settings, conversation)
            for reply in replies:
                await _deliver(channel, reply)
        try:
            await channel.answer_callbacks()
        except Exception:
            logger.info("telegram callback", extra={"kind": "channel.callback", "ok": False})
    return Response(status_code=200)


def _update_id(body: bytes) -> int | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    update_id = payload.get("update_id") if isinstance(payload, dict) else None
    return update_id if isinstance(update_id, int) else None


def build_run_context(settings: Settings, app=None):
    """Build the job runner's context once. Missing credentials leave a part out, never fake."""
    from app.engine.runner import RunContext

    mailbox = None
    if settings.family_mailbox and settings.google_refresh_token_family.get_secret_value():
        try:
            from app.integrations.google import gmail_mailbox_for

            mailbox = gmail_mailbox_for(settings, "family")
        except Exception:
            logger.info("mailbox build", extra={"kind": "job.context", "ok": False})
    ai = None
    if settings.openai_api_key.get_secret_value():
        from app.ai.client import AgentsSDKClient

        ai = AgentsSDKClient(settings)
    notify = ask = None
    if app is not None:

        async def notify(text: str) -> bool:
            return await notify_owner(app, text)

        async def ask(text: str, buttons: list[tuple[str, str]]) -> bool:
            return await notify_owner(app, text, buttons=buttons)

    return RunContext(settings=settings, mailbox=mailbox, ai=ai, notify=notify, ask=ask)


async def supervise(
    stop: asyncio.Event, database_url: str, poll_seconds: int, app=None, settings=None
) -> None:
    """Run due jobs until stopped. The log records the kind, not the error text."""
    if not database_url:
        return
    from app.db import make_engine
    from app.engine import executors as _engine_executors  # noqa: F401  (registers kinds)
    from app.engine.runner import now_utc, register_executor, run_due_jobs
    from app.mail.jobs import register_mail_executors

    register_mail_executors(register_executor)
    settings = settings or getattr(getattr(app, "state", None), "settings", None) or Settings()
    ctx = build_run_context(settings, app)
    engine = make_engine(database_url)

    def factory() -> Session:
        return Session(engine)

    try:
        while not stop.is_set():
            try:
                await run_due_jobs(factory, ctx, wall=now_utc())
            except Exception:
                logger.info("job tick", extra={"kind": "job.tick", "ok": False})
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                continue
    finally:
        engine.dispose()
