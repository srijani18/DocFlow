"""SQL for extractions. Append-only: there is no update or delete (ADR-0005)."""

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.extractions.exact_json import dumps_exact
from app.extractions.models import Extraction


async def find_model_extraction(
    session: AsyncSession, scope: WorkspaceScope, document_id: uuid.UUID, generation: int
) -> Extraction | None:
    extraction: Extraction | None = await session.scalar(
        select(Extraction).where(
            Extraction.workspace_id == scope.workspace_id,
            Extraction.document_id == document_id,
            Extraction.processing_generation == generation,
            Extraction.source == "model",
        )
    )
    return extraction


async def insert_version(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    source: str,
    schema_id: str,
    data: dict[str, Any],
    confidence: dict[str, Any],
    prompt_version: str | None,
    llm_call_id: uuid.UUID | None,
    generation: int,
    created_by_user_id: uuid.UUID | None,
) -> Extraction:
    next_version = (
        select(func.coalesce(func.max(Extraction.version), 0) + 1)
        .where(Extraction.workspace_id == scope.workspace_id, Extraction.document_id == document_id)
        .scalar_subquery()
    )
    extraction: Extraction = (
        await session.scalars(
            insert(Extraction)
            .values(
                workspace_id=scope.workspace_id,
                document_id=document_id,
                version=next_version,
                source=source,
                schema_id=schema_id,
                # Exact JSON text, cast in SQL: amounts never pass through a float (F5 AC8).
                data=cast(literal(dumps_exact(data)), JSONB),
                confidence=cast(literal(dumps_exact(confidence)), JSONB),
                prompt_version=prompt_version,
                llm_call_id=llm_call_id,
                processing_generation=generation,
                created_by_user_id=created_by_user_id,
            )
            .returning(Extraction)
        )
    ).one()
    return extraction


async def get_by_id(
    session: AsyncSession, scope: WorkspaceScope, extraction_id: uuid.UUID
) -> Extraction | None:
    extraction: Extraction | None = await session.scalar(
        select(Extraction).where(
            Extraction.workspace_id == scope.workspace_id, Extraction.id == extraction_id
        )
    )
    return extraction


async def get_exact_data(
    session: AsyncSession, scope: WorkspaceScope, extraction_id: uuid.UUID
) -> dict[str, Any]:
    """The version's data with amounts as Decimals, read as JSON text so no float is involved."""
    text = await session.scalar(
        select(cast(Extraction.data, Text)).where(
            Extraction.workspace_id == scope.workspace_id, Extraction.id == extraction_id
        )
    )
    if text is None:
        raise LookupError(extraction_id)
    data: dict[str, Any] = json.loads(text, parse_float=Decimal)
    return data
