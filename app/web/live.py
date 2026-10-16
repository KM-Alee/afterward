"""Fan out desk events to WebSocket subscribers. Payloads follow the audit secrecy rule."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

from app.contracts import json_payload

Subscriber = Callable[[dict[str, object]], None]


class LiveHub:
    """In-process fan-out. A published event is delivered to every subscriber."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, object]]]] = defaultdict(list)
        self._callbacks: dict[str, list[Subscriber]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None
        self.on_change: Callable[[], None] | None = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe_queue(self, case_id: UUID) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._queues[str(case_id)].append(queue)
        return queue

    def unsubscribe_queue(self, case_id: UUID, queue: asyncio.Queue[dict[str, object]]) -> None:
        listeners = self._queues.get(str(case_id), [])
        if queue in listeners:
            listeners.remove(queue)

    def subscribe(self, case_id: UUID, callback: Subscriber) -> None:
        self._callbacks[str(case_id)].append(callback)

    def publish(
        self,
        case_id: UUID,
        kind: str,
        payload: dict[str, object],
        *,
        actor: str = "desk",
    ) -> dict[str, object]:
        """Screen the payload, then hand it to queues and callbacks."""
        message: dict[str, object] = {
            "kind": kind,
            "actor": actor,
            "case_id": str(case_id),
            "payload": json_payload(payload),
        }
        loop = self._loop

        def _fanout() -> None:
            for queue in list(self._queues.get(str(case_id), ())):
                queue.put_nowait(message)
            for callback in list(self._callbacks.get(str(case_id), ())):
                callback(message)

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_fanout)
        else:
            _fanout()
        if self.on_change is not None:
            with contextlib.suppress(Exception):
                self.on_change()
        return message
