"""SQL for validation issues and the workspace lookups behind the duplicate and
known-vendor checks (F6 plan §3)."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, DocumentStatus
from app.extractions.models import Extraction
from app.validation.models import ValidationIssue


def _party_gstin() -> ColumnElement[str | None]:
    return func.coalesce(
        Extraction.data["vendor"]["gstin"].astext, Extraction.data["merchant"]["gstin"].astext
    )


def _same_vendor(gstin: str | None, name: str | None) -> ColumnElement[bool]:
    matches = []
    if gstin:
        matches.append(_party_gstin() == gstin)
    if name:
        matches.append(func.lower(Document.vendor_name) == name.lower())
    return or_(*matches)


async def find_duplicates(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    doc_type: str,
    number_field: str,
    number: str,
    gstin: str | None,
    name: str | None,
) -> list[uuid.UUID]:
    """Other documents of this type and number from the same vendor, by GSTIN or name."""
    if not gstin and not name:
        return []
    rows = await session.scalars(
        select(Document.id)
        .join(Extraction, Extraction.id == Document.current_extraction_id)
        .where(
            Document.workspace_id == scope.workspace_id,
            Extraction.workspace_id == scope.workspace_id,
            Document.id != document_id,
            Document.doc_type == doc_type,
            Extraction.data[number_field].astext == number,
            _same_vendor(gstin, name),
        )
    )
    return list(rows)


async def vendor_seen(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    gstin: str | None,
    name: str | None,
) -> bool:
    """Whether the vendor is on an earlier approved document in the workspace."""
    if not gstin and not name:
        return False
    found = await session.scalar(
        select(Document.id)
        .join(Extraction, Extraction.id == Document.current_extraction_id)
        .where(
            Document.workspace_id == scope.workspace_id,
            Extraction.workspace_id == scope.workspace_id,
            Document.id != document_id,
            Document.status == DocumentStatus.APPROVED,
            _same_vendor(gstin, name),
        )
        .limit(1)
    )
    return found is not None


async def insert_issues(
    session: AsyncSession, scope: WorkspaceScope, rows: Sequence[dict[str, object]]
) -> None:
    if rows:
        await session.execute(
            insert(ValidationIssue).values(
                [{**row, "workspace_id": scope.workspace_id} for row in rows]
            )
        )


async def list_for_extraction(
    session: AsyncSession, scope: WorkspaceScope, extraction_id: uuid.UUID
) -> list[ValidationIssue]:
    rows = await session.scalars(
        select(ValidationIssue)
        .where(
            ValidationIssue.workspace_id == scope.workspace_id,
            ValidationIssue.extraction_id == extraction_id,
        )
        .order_by(ValidationIssue.created_at, ValidationIssue.id)
    )
    return list(rows)


async def open_counts(
    session: AsyncSession, scope: WorkspaceScope, extraction_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """Unfixed issues per extraction and severity."""
    if not extraction_ids:
        return {}
    rows = await session.execute(
        select(ValidationIssue.extraction_id, ValidationIssue.severity, func.count())
        .where(
            ValidationIssue.workspace_id == scope.workspace_id,
            ValidationIssue.extraction_id.in_(list(extraction_ids)),
            ValidationIssue.fixed_by_agent.is_(False),
        )
        .group_by(ValidationIssue.extraction_id, ValidationIssue.severity)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for extraction_id, severity, count in rows:
        counts.setdefault(extraction_id, {})[severity] = count
    return counts
