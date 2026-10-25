"""The server-sent event stream (F3 plan §2): `ready` on connect, `document.status` per
change, a keep-alive comment every 15 s, and a close after 30 minutes (F3 spec D4)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from app.core.clock import Clock
from app.documents.schemas import DocumentStatusEvent
from app.documents.service import StatusEvent
from app.events.broker import Subscription

KEEPALIVE_SECONDS = 15.0
MAX_STREAM_SECONDS = 30 * 60.0


def format_event(event: StatusEvent) -> str:
    data = DocumentStatusEvent(
        document_id=event.document_id,
        status=event.status,  # type: ignore[arg-type]
        failure_reason=event.failure_reason,
        changed_at=event.changed_at,
    ).model_dump_json()
    return f"event: document.status\ndata: {data}\n\n"


async def event_stream(
    subscription: Subscription,
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
    clock: Clock,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
    max_seconds: float = MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    # On connect (and every reconnect) the browser refetches, so missed events don't matter.
    yield "event: ready\ndata: {}\n\n"
    started = clock.now()
    while (clock.now() - started).total_seconds() < max_seconds:
        if subscription.overflowed.is_set() or await is_disconnected():
            return
        try:
            async with asyncio.timeout(keepalive_seconds):
                event = await subscription.queue.get()
        except TimeoutError:
            yield ": keep-alive\n\n"
            continue
        yield format_event(event)
