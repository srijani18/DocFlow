"""`Idempotency-Key` on write endpoints (F14 AC6, AC7, plan §3).

A write sent with the header is claimed before the endpoint runs, in its own short
transaction, so a concurrent duplicate sees the claim:
- same key, same request, finished: the stored response is replayed, with
  `Idempotent-Replayed: true`, and nothing runs again;
- same key, still running: 409 with `Retry-After`;
- same key, different request: 422.

A successful response is stored. An error releases the key, so a retry can run. Keys last 24
hours. A claim left `running` by a crash is ignored after a minute. Without the header,
nothing changes.
"""

import hashlib
import uuid
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import WorkspaceScopeDep
from app.core.errors import AppError
from app.core.tenancy import WorkspaceScope
from app.idempotency.models import KEEP_FOR, IdempotencyKey

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
MAX_KEY_LENGTH = 255
STALE_AFTER = timedelta(minutes=1)
_STATE = "idempotency_key_id"

SessionOpener = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class IdempotencyKeyReusedError(AppError):
    status = 422
    type_slug = "idempotency-key-reused"
    title = "This Idempotency-Key was already used for a different request"


class IdempotencyKeyInProgressError(AppError):
    status = 409
    type_slug = "idempotency-key-in-progress"
    title = "A request with this Idempotency-Key is still running"


class InvalidIdempotencyKeyError(AppError):
    status = 422
    type_slug = "invalid-idempotency-key"
    title = f"Idempotency-Key must be 1 to {MAX_KEY_LENGTH} visible characters"


class Replay(Exception):  # noqa: N818  # not an error: a stored answer to send back
    def __init__(self, *, status: int, media_type: str | None, body: str) -> None:
        super().__init__(status)
        self.status = status
        self.media_type = media_type
        self.body = body


def sessions(request: Request) -> SessionOpener:
    """Separate short transactions; tests point this at their own session."""
    opener: SessionOpener = getattr(
        request.app.state, "idempotency_sessions", request.app.state.sessionmaker
    )
    return opener


async def _claim(
    open_session: SessionOpener, scope: WorkspaceScope, key: str, request_hash: str
) -> uuid.UUID | Replay:
    async with open_session() as session:
        # Expired keys and claims abandoned by a crash don't count.
        await session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.workspace_id == scope.workspace_id,
                IdempotencyKey.user_id == scope.user_id,
                IdempotencyKey.key == key,
                or_(
                    IdempotencyKey.created_at < func.now() - KEEP_FOR,
                    (IdempotencyKey.status == "running")
                    & (IdempotencyKey.updated_at < func.now() - STALE_AFTER),
                ),
            )
        )
        claimed: uuid.UUID | None = await session.scalar(
            insert(IdempotencyKey)
            .values(
                workspace_id=scope.workspace_id,
                user_id=scope.user_id,
                key=key,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(index_elements=["workspace_id", "user_id", "key"])
            .returning(IdempotencyKey.id)
        )
        existing = None
        if claimed is None:
            existing = await session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.workspace_id == scope.workspace_id,
                    IdempotencyKey.user_id == scope.user_id,
                    IdempotencyKey.key == key,
                )
            )
        await session.commit()
    if claimed is not None:
        return claimed
    if existing is not None and existing.request_hash != request_hash:
        raise IdempotencyKeyReusedError()
    if existing is None or existing.status == "running":  # None: it expired just now
        raise IdempotencyKeyInProgressError(headers={"Retry-After": "1"})
    return Replay(
        status=existing.response_status or 200,
        media_type=existing.response_type,
        body=existing.response_body or "",
    )


async def idempotent(
    request: Request,
    scope: WorkspaceScopeDep,
    key: Annotated[
        str | None,
        Header(
            alias=HEADER,
            description="Optional. A repeat with the same key within 24 hours returns the "
            "first response instead of acting again.",
        ),
    ] = None,
) -> None:
    """Route dependency. Runs after the workspace is resolved, so keys belong to a member."""
    if key is None:
        return
    if not 0 < len(key) <= MAX_KEY_LENGTH or not key.isprintable() or key.strip() != key:
        raise InvalidIdempotencyKeyError()
    digest = hashlib.sha256()
    for part in (request.method.encode(), request.url.path.encode(), await request.body()):
        digest.update(part)
        digest.update(b"\0")
    outcome = await _claim(sessions(request), scope, key, digest.hexdigest())
    if isinstance(outcome, Replay):
        raise outcome
    setattr(request.state, _STATE, outcome)


Idempotent = Annotated[None, Depends(idempotent)]


async def _finish(request: Request, response: Response | None) -> None:
    claim_id = getattr(request.state, _STATE, None)
    if claim_id is None:
        return
    async with sessions(request)() as session:
        if response is not None and response.status_code < 400:
            await session.execute(
                update(IdempotencyKey)
                .where(IdempotencyKey.id == claim_id)
                .values(
                    status="done",
                    response_status=response.status_code,
                    response_type=response.media_type,
                    response_body=bytes(response.body).decode(),
                    updated_at=func.now(),
                )
            )
        else:  # failed: let a retry run
            await session.execute(delete(IdempotencyKey).where(IdempotencyKey.id == claim_id))
        await session.commit()


class IdempotentRoute(APIRoute):
    """Stores the response of routes that use the `Idempotent` dependency."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                response = await handle(request)
            except Exception:
                await _finish(request, None)
                raise
            await _finish(request, response)
            return response

        return route


async def _replay(_request: Request, exc: Exception) -> Response:
    if not isinstance(exc, Replay):  # registered for Replay only; narrows for mypy
        raise exc
    return Response(
        content=exc.body,
        status_code=exc.status,
        media_type=exc.media_type,
        headers={REPLAYED_HEADER: "true"},
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(Replay, _replay)
