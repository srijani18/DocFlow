"""SQL for corrections and the review metrics (F7 plan §2)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import cast, distinct, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, DocumentStatus
from app.extractions.exact_json import dumps_exact
from app.extractions.models import Extraction
from app.review.diff import Change
from app.review.models import Correction


async def insert_corrections(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    changes: Sequence[Change],
) -> None:
    if not changes:
        return
    await session.execute(
        insert(Correction).values(
            [
                {
                    "workspace_id": scope.workspace_id,
                    "document_id": document_id,
                    "extraction_id": extraction_id,
                    "path": change.path,
                    # Exact JSON, cast in SQL, like extraction data (F5 AC8).
                    "old_value": cast(literal(dumps_exact(change.old)), JSONB),
                    "new_value": cast(literal(dumps_exact(change.new)), JSONB),
                    "user_id": scope.user_id,
                }
                for change in changes
            ]
        )
    )


async def approval_counts(session: AsyncSession, scope: WorkspaceScope) -> tuple[int, int, int]:
    """(approved, approved with at least one correction, approved by the agent)."""
    approved = await session.scalar(
        select(func.count()).where(
            Document.workspace_id == scope.workspace_id,
            Document.status == DocumentStatus.APPROVED,
        )
    )
    by_agent = await session.scalar(
        select(func.count()).where(
            Document.workspace_id == scope.workspace_id,
            Document.status == DocumentStatus.APPROVED,
            Document.approved_by_agent.is_(True),
        )
    )
    edited = await session.scalar(
        select(func.count(distinct(Correction.document_id)))
        .join(Document, Document.id == Correction.document_id)
        .where(
            Correction.workspace_id == scope.workspace_id,
            Document.workspace_id == scope.workspace_id,
            Document.status == DocumentStatus.APPROVED,
        )
    )
    return approved or 0, edited or 0, by_agent or 0


async def approved_by_people(
    session: AsyncSession, scope: WorkspaceScope
) -> list[tuple[Document, Extraction, int]]:
    """Documents a person approved, with the approved version and how many fields they
    corrected, oldest first."""
    corrections = (
        select(func.count())
        .where(Correction.workspace_id == scope.workspace_id, Correction.document_id == Document.id)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Document, Extraction, corrections)
        .join(Extraction, Extraction.id == Document.approved_extraction_id)
        .where(
            Document.workspace_id == scope.workspace_id,
            Extraction.workspace_id == scope.workspace_id,
            Document.status == DocumentStatus.APPROVED,
            Document.approved_by_user_id.is_not(None),
        )
        .order_by(Document.approved_at, Document.id)
    )
    return [(document, extraction, count) for document, extraction, count in rows]
