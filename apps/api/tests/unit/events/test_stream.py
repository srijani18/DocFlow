import asyncio
import json
import uuid
from datetime import UTC, datetime

from app.documents.service import StatusEvent
from app.events.broker import QUEUE_SIZE, EventBroker
from app.events.stream import event_stream
from tests.support.clock import FrozenClock

WS_A, WS_B = uuid.uuid4(), uuid.uuid4()


def status_event(workspace_id: uuid.UUID, status: str = "CLASSIFYING") -> StatusEvent:
    return StatusEvent(
        workspace_id=workspace_id,
        document_id=uuid.uuid4(),
        status=status,
        failure_reason=None,
        changed_at=datetime(2026, 10, 25, tzinfo=UTC),
    )


async def connected() -> bool:
    return False


async def test_ac9_status_change_streamed() -> None:
    broker = EventBroker()
    with broker.subscribe(WS_A) as subscription:
        stream = event_stream(subscription, is_disconnected=connected, clock=FrozenClock())
        assert await anext(stream) == "event: ready\ndata: {}\n\n"

        event = status_event(WS_A)
        broker.publish(event)
        chunk = await anext(stream)

    name, data = chunk.strip().split("\n")
    assert name == "event: document.status"
    payload = json.loads(data.removeprefix("data: "))
    assert payload == {
        "document_id": str(event.document_id),
        "status": "CLASSIFYING",
        "failure_reason": None,
        "changed_at": "2026-10-25T00:00:00Z",
    }


async def test_ac10_other_workspace_events_not_streamed() -> None:
    broker = EventBroker()
    with broker.subscribe(WS_A) as a, broker.subscribe(WS_B) as b:
        broker.publish(status_event(WS_B))

        assert a.queue.empty()
        assert b.queue.qsize() == 1


async def test_sse_keepalive_and_max_duration() -> None:
    broker = EventBroker()
    clock = FrozenClock()
    with broker.subscribe(WS_A) as subscription:
        stream = event_stream(
            subscription,
            is_disconnected=connected,
            clock=clock,
            keepalive_seconds=0.01,
            max_seconds=60,
        )
        await anext(stream)  # ready
        assert await anext(stream) == ": keep-alive\n\n"

        clock.advance(seconds=61)
        chunks = [chunk async for chunk in stream]

    assert chunks == []  # closed after the maximum duration; the browser reconnects


async def test_stream_stops_when_client_disconnects() -> None:
    broker = EventBroker()

    async def gone() -> bool:
        return True

    with broker.subscribe(WS_A) as subscription:
        stream = event_stream(subscription, is_disconnected=gone, clock=FrozenClock())
        await anext(stream)
        assert [chunk async for chunk in stream] == []


async def test_slow_subscriber_is_disconnected_not_buffered_forever() -> None:
    broker = EventBroker()
    with broker.subscribe(WS_A) as subscription:
        for _ in range(QUEUE_SIZE + 1):
            broker.publish(status_event(WS_A))

        assert subscription.overflowed.is_set()
        stream = event_stream(subscription, is_disconnected=connected, clock=FrozenClock())
        await anext(stream)
        assert [chunk async for chunk in stream] == []
    assert broker.subscriber_count(WS_A) == 0


async def test_unsubscribe_cleans_up() -> None:
    broker = EventBroker()
    with broker.subscribe(WS_A):
        assert broker.subscriber_count(WS_A) == 1
    assert broker.subscriber_count(WS_A) == 0
    await asyncio.sleep(0)
