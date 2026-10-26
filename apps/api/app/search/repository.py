"""SQL for search (F8 plan §2). Every query is limited to one workspace (AC9)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document
from app.search.models import DocumentEmbedding

SIMPLE: ColumnElement[Any] = literal_column("'simple'::regconfig")


async def embedded_version(
    session: AsyncSession, scope: WorkspaceScope, document_id: uuid.UUID
) -> uuid.UUID | None:
    """The extraction version the document's embedding was made from, if any."""
    version: uuid.UUID | None = await session.scalar(
        select(DocumentEmbedding.extraction_id).where(
            DocumentEmbedding.workspace_id == scope.workspace_id,
            DocumentEmbedding.document_id == document_id,
        )
    )
    return version


@dataclass(frozen=True)
class Filters:
    """F8 AC4. Each is optional; together they narrow the results."""

    doc_type: str | None = None
    status: str | None = None
    vendor: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None

    def conditions(self, scope: WorkspaceScope) -> list[ColumnElement[bool]]:
        conditions = [Document.workspace_id == scope.workspace_id]
        if self.doc_type:
            conditions.append(Document.doc_type == self.doc_type)
        if self.status:
            conditions.append(Document.status == self.status)
        if self.vendor:
            escaped = self.vendor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(Document.vendor_name.ilike(f"%{escaped}%", escape="\\"))
        if self.date_from:
            conditions.append(Document.document_date >= self.date_from)
        if self.date_to:
            conditions.append(Document.document_date <= self.date_to)
        if self.amount_min is not None:
            conditions.append(Document.total_amount >= self.amount_min)
        if self.amount_max is not None:
            conditions.append(Document.total_amount <= self.amount_max)
        return conditions


async def keyword_matches(
    session: AsyncSession, scope: WorkspaceScope, tsquery: str, filters: Filters, *, limit: int
) -> list[tuple[uuid.UUID, str]]:
    """(document id, snippet), best first."""
    query = func.to_tsquery(SIMPLE, tsquery)
    snippet = func.ts_headline(
        SIMPLE,
        Document.search_text,
        query,
        "StartSel=[[, StopSel=]], MaxWords=14, MinWords=4, MaxFragments=1",
    )
    rows = await session.execute(
        select(Document.id, snippet)
        .where(*filters.conditions(scope), Document.search_vector.op("@@")(query))
        .order_by(func.ts_rank_cd(Document.search_vector, query).desc(), Document.id)
        .limit(limit)
    )
    return [(document_id, text) for document_id, text in rows]


async def semantic_distances(
    session: AsyncSession,
    scope: WorkspaceScope,
    vector: list[float],
    filters: Filters,
    *,
    limit: int,
) -> list[tuple[uuid.UUID, float]]:
    """(document id, cosine distance), closest first. The search eval reads the distances
    to choose the cut-off (AC10)."""
    distance = DocumentEmbedding.embedding.cosine_distance(vector)
    rows = await session.execute(
        select(Document.id, distance)
        .join(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
        .where(
            *filters.conditions(scope),
            DocumentEmbedding.workspace_id == scope.workspace_id,
            # Only the version on screen: a stale embedding would match old values.
            DocumentEmbedding.extraction_id == Document.current_extraction_id,
        )
        .order_by(distance, Document.id)
        .limit(limit)
    )
    return [(document_id, float(value)) for document_id, value in rows]


async def newest(
    session: AsyncSession, scope: WorkspaceScope, filters: Filters, *, offset: int, limit: int
) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(Document.id)
        .where(*filters.conditions(scope))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows)


async def documents_by_id(
    session: AsyncSession, scope: WorkspaceScope, ids: list[uuid.UUID]
) -> list[Document]:
    """In the order given."""
    if not ids:
        return []
    rows = await session.scalars(
        select(Document).where(Document.workspace_id == scope.workspace_id, Document.id.in_(ids))
    )
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]
