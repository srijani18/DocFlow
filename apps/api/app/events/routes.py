"""Live document status over server-sent events (F3 AC9, AC10)."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import EVENT_STREAM_SUFFIX, WorkspaceScopeDep
from app.core.errors import problem_responses
from app.events.dependencies import EventsDep
from app.events.stream import event_stream
from app.storage.dependencies import ClockDep

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["events"])


@router.get(
    EVENT_STREAM_SUFFIX,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "`ready`, then `document.status` events (DocumentStatusEvent JSON)",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **problem_responses(401, 404, 503),
    },
)
async def stream_events(
    scope: WorkspaceScopeDep, request: Request, events: EventsDep, clock: ClockDep
) -> StreamingResponse:
    """Status changes for the caller's workspace only. The membership check (and its
    database session) finishes before streaming starts, so no connection is held open."""

    async def body() -> AsyncIterator[str]:
        # Subscribed by workspace from the verified scope, never from client input (AC10).
        with events.subscribe(scope.workspace_id) as subscription:
            async for chunk in event_stream(
                subscription, is_disconnected=request.is_disconnected, clock=clock
            ):
                yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
