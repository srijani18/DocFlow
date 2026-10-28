"""Queue facade for other modules (ADR-0002)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.jobs import repository


async def enqueue_document_processing(
    session: AsyncSession, scope: WorkspaceScope, *, document_id: uuid.UUID, generation: int
) -> uuid.UUID | None:
    """Queue a processing run, in the caller's transaction (ADR-0001: the document and its
    job commit together)."""
    return await repository.enqueue(session, scope, document_id=document_id, generation=generation)


async def enqueue_embedding(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
) -> uuid.UUID | None:
    """Queue the search embedding of a new current version, in the caller's transaction."""
    return await repository.enqueue_embedding(
        session, scope, document_id=document_id, extraction_id=extraction_id
    )
