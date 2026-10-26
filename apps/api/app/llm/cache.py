"""Response cache (F10 AC6, spec D4): only validated answers, never across workspaces."""

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import LlmCacheEntry
from app.llm.routing import RouteEntry
from app.llm.types import FilePart, LlmRequest, TextPart


def cache_key(request: LlmRequest, route: Sequence[RouteEntry]) -> str:
    """Same workspace, task, prompt version, content, schema and route → same key."""
    digest = hashlib.sha256()
    for piece in (
        str(request.context.workspace_id),  # never shared between workspaces
        request.task,
        request.prompt.version,
        ",".join(map(str, route)),
        json.dumps(request.response_schema, sort_keys=True, default=str),
    ):
        digest.update(piece.encode())
        digest.update(b"\x00")
    for part in request.parts:
        if isinstance(part, TextPart):
            digest.update(b"text:" + part.text.encode())
        elif isinstance(part, FilePart):
            digest.update(b"file:" + part.mime_type.encode() + hashlib.sha256(part.data).digest())
    return digest.hexdigest()


async def lookup(
    session: AsyncSession, key: str, workspace_id: uuid.UUID, *, ttl: timedelta
) -> LlmCacheEntry | None:
    entry: LlmCacheEntry | None = await session.scalar(
        select(LlmCacheEntry).where(
            LlmCacheEntry.key == key,
            LlmCacheEntry.workspace_id == workspace_id,
            LlmCacheEntry.created_at > func.now() - ttl,
        )
    )
    return entry


async def store(
    session: AsyncSession,
    *,
    key: str,
    workspace_id: uuid.UUID,
    task: str,
    provider: str,
    model: str,
    raw_json: str,
    source_call_id: uuid.UUID,
    ttl: timedelta,
) -> None:
    # Expired entries of this workspace are removed as new ones arrive, so the table
    # stays small without a separate cleanup job.
    await session.execute(
        delete(LlmCacheEntry).where(
            LlmCacheEntry.workspace_id == workspace_id, LlmCacheEntry.created_at <= func.now() - ttl
        )
    )
    values = {
        "workspace_id": workspace_id,
        "task": task,
        "provider": provider,
        "model": model,
        "raw_json": raw_json,
        "source_call_id": source_call_id,
    }
    await session.execute(
        insert(LlmCacheEntry)
        .values(key=key, **values)
        .on_conflict_do_update(
            index_elements=[LlmCacheEntry.key], set_={**values, "created_at": func.now()}
        )
    )
