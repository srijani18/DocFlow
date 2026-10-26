"""SQL for export (F9 plan §3): documents with the data of the version to export."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Text, cast, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, DocumentStatus
from app.extractions.models import Extraction
from app.identity.models import User
from app.review.models import Correction
from app.search.repository import Filters


def _statement(scope: WorkspaceScope, filters: Filters, *, include_unapproved: bool) -> Any:
    corrections = (
        select(func.count())
        .where(Correction.workspace_id == scope.workspace_id, Correction.document_id == Document.id)
        .scalar_subquery()
    )
    statement = (
        select(Document, cast(Extraction.data, Text), User.email, corrections)
        # The approved version (AC8); a document not yet approved exports its current one.
        .join(
            Extraction,
            Extraction.id
            == func.coalesce(Document.approved_extraction_id, Document.current_extraction_id),
        )
        .outerjoin(User, User.id == Document.approved_by_user_id)
        .where(*filters.conditions(scope), Extraction.workspace_id == scope.workspace_id)
    )
    if not include_unapproved:
        statement = statement.where(Document.status == DocumentStatus.APPROVED)
    return statement


async def count(
    session: AsyncSession,
    scope: WorkspaceScope,
    filters: Filters,
    *,
    include_unapproved: bool,
    ids: Sequence[uuid.UUID] | None,
) -> int:
    statement = _statement(scope, filters, include_unapproved=include_unapproved)
    if ids is not None:
        statement = statement.where(Document.id.in_(list(ids)))
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    return total or 0


Row = tuple[Document, str, str | None, int]


async def page(  # one page of an export needs all of this
    session: AsyncSession,
    scope: WorkspaceScope,
    filters: Filters,
    *,
    include_unapproved: bool,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[Row]:
    """Newest first, keyset-paged on (created_at, id)."""
    statement = _statement(scope, filters, include_unapproved=include_unapproved)
    if after is not None:
        statement = statement.where(tuple_(Document.created_at, Document.id) < after)
    statement = statement.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)
    return [tuple(row) for row in await session.execute(statement)]


async def by_ids(
    session: AsyncSession,
    scope: WorkspaceScope,
    filters: Filters,
    *,
    include_unapproved: bool,
    ids: Sequence[uuid.UUID],
) -> list[Row]:
    """These documents, in the order given (search ranking)."""
    statement = _statement(scope, filters, include_unapproved=include_unapproved).where(
        Document.id.in_(list(ids))
    )
    rows: dict[uuid.UUID, Row] = {row[0].id: tuple(row) for row in await session.execute(statement)}
    return [rows[i] for i in ids if i in rows]
