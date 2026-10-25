"""In-process pub/sub for document status events (F3 plan §1).

Works while the API and the worker share a process (ROLE=all). After a split (ADR-0002)
the same interface is backed by Postgres LISTEN/NOTIFY.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.logging import get_logger
from app.documents.service import StatusEvent

log = get_logger(__name__)

QUEUE_SIZE = 100


class Subscription:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[StatusEvent] = asyncio.Queue(maxsize=QUEUE_SIZE)
        # Set when this subscriber fell too far behind; the stream then closes and the
        # browser reconnects and refetches, so a slow tab can't grow memory.
        self.overflowed = asyncio.Event()


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[Subscription]] = defaultdict(set)

    @contextmanager
    def subscribe(self, workspace_id: uuid.UUID) -> Iterator[Subscription]:
        subscription = Subscription()
        self._subscribers[workspace_id].add(subscription)
        try:
            yield subscription
        finally:
            self._subscribers[workspace_id].discard(subscription)
            if not self._subscribers[workspace_id]:
                del self._subscribers[workspace_id]

    def publish(self, event: StatusEvent) -> None:
        """Deliver to the event's own workspace only (F3 AC10). Call after commit."""
        for subscription in list(self._subscribers.get(event.workspace_id, ())):
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("event_subscriber_overflow", workspace_id=str(event.workspace_id))
                subscription.overflowed.set()

    def subscriber_count(self, workspace_id: uuid.UUID) -> int:
        return len(self._subscribers.get(workspace_id, ()))
