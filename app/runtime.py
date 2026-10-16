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


def _conversation(settings: Settings):
    from app.ai.client import AgentsSDKClient
    from app.conversation.demo_malik import ALLOWED_RECIPIENTS, INVITE_TOKEN, NORTHLINE, PROVIDERS
    from app.conversation.session import Conversation, Invite

    return Conversation(
        AgentsSDKClient(settings, timeout_s=60, max_retries=1),
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
    await conversation.ingest_picture(
        image=data,
        mime=mime,
        label=event.text or "photo from the family",
        evidence="telegram",
        cipher=cipher,
    )
    return [Outbound(event.sender, "I saved that picture with the case documents.")]


async def after_turn(app, conversation, sender: str, replies: list) -> list:
    """Continue the Malik story the desk shows: ask Amina, mirror the turn, send on approval."""
    from app.conversation.session import Outbound
    from app.story import mark_request_sent, reflect_turn

    kinds = [reply.kind for reply in replies]
    if "invite_joined" in kinds:
        asked = conversation.ask_dependency(sender)
        replies = [*replies, *asked]
        kinds += [reply.kind for reply in asked]
    surface = getattr(app.state, "surface", None)
    if surface is None:
        return replies
    reflect_turn(surface, conversation, kinds)
    if "approval_recorded" in kinds:
        text = await mark_request_sent(
            surface, getattr(app.state, "settings", None), conversation.state.approval
        )
        replies = [*replies, Outbound(sender, text, kind="request_sent")]
    return replies


async def notify_owner(app, text: str) -> bool:
    """Tell Sara in Telegram when a provider reply was checked. No-op without a chat."""
    conversation = getattr(app.state, "conversation", None)
    channel = getattr(app.state, "telegram_channel", None)
    owner = getattr(getattr(conversation, "state", None), "owner_sender", None)
    if conversation is None or channel is None or not owner:
        return False
    from app.conversation.session import Outbound

    await _deliver(channel, Outbound(owner, text))
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
    seen = getattr(request.app.state, "telegram_updates", None)
    if seen is None:
        seen = set()
        request.app.state.telegram_updates = seen
    if update_id is not None and update_id in seen:
        return Response(status_code=200)
    if update_id is not None:
        seen.add(update_id)
    if not settings.openai_api_key.get_secret_value() or not events:
        return Response(status_code=200)
    conversation = getattr(request.app.state, "conversation", None)
    if conversation is None:
        conversation = _conversation(settings)
        request.app.state.conversation = conversation
    lock = getattr(request.app.state, "conversation_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.conversation_lock = lock
    cipher = _cipher(settings)
    async with lock:
        for event in events:
            try:
                replies = await replies_for(conversation, channel, event, cipher=cipher)
                replies = await after_turn(request.app, conversation, event.sender, replies)
            except Exception:
                logger.info("telegram turn", extra={"kind": "channel.turn", "ok": False})
                continue
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


async def supervise(stop: asyncio.Event, database_url: str, poll_seconds: int) -> None:
    """Run health checks until stopped. The log records the kind, not the error text."""
    if not database_url:
        return
    from app.db import make_engine

    engine = make_engine(database_url)
    try:
        while not stop.is_set():
            try:
                with Session(engine) as session:
                    run_health_checks(session)
                    session.commit()
            except Exception:
                logger.info("health tick", extra={"kind": "job.health", "ok": False})
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                continue
    finally:
        engine.dispose()
