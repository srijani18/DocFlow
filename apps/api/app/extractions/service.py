"""Extraction rules (F5). Other modules use this facade (ADR-0002)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents
from app.extractions import repository
from app.extractions.models import Extraction
from app.extractions.summary import summarize


async def find_model_extraction(
    session: AsyncSession, scope: WorkspaceScope, document_id: uuid.UUID, generation: int
) -> Extraction | None:
    """The model's extraction from this processing run, if one was stored (F5 AC5)."""
    return await repository.find_model_extraction(session, scope, document_id, generation)


async def get_exact_data(
    session: AsyncSession, scope: WorkspaceScope, extraction_id: uuid.UUID
) -> dict[str, Any]:
    return await repository.get_exact_data(session, scope, extraction_id)


async def record_model_extraction(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    doc_type: str,
    schema_id: str,
    data: dict[str, Any],
    confidence: dict[str, Any],
    prompt_version: str,
    llm_call_id: uuid.UUID,
    generation: int,
) -> Extraction:
    """Store a new version and make it current, with the document's summary fields."""
    return await _record_version(
        session,
        scope,
        document_id=document_id,
        source="model",
        doc_type=doc_type,
        schema_id=schema_id,
        data=data,
        confidence=confidence,
        prompt_version=prompt_version,
        llm_call_id=llm_call_id,
        generation=generation,
    )


async def record_agent_fix(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    doc_type: str,
    schema_id: str,
    data: dict[str, Any],
    confidence: dict[str, Any],
    prompt_version: str,
    llm_call_id: uuid.UUID | None,
    generation: int,
) -> Extraction:
    """The validation agent's corrected version, made current (F6 AC3)."""
    return await _record_version(
        session,
        scope,
        document_id=document_id,
        source="agent_fix",
        doc_type=doc_type,
        schema_id=schema_id,
        data=data,
        confidence=confidence,
        prompt_version=prompt_version,
        llm_call_id=llm_call_id,
        generation=generation,
    )


async def _record_version(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    source: str,
    doc_type: str,
    schema_id: str,
    data: dict[str, Any],
    confidence: dict[str, Any],
    prompt_version: str,
    llm_call_id: uuid.UUID | None,
    generation: int,
) -> Extraction:
    extraction = await repository.insert_version(
        session,
        scope,
        document_id=document_id,
        source=source,
        schema_id=schema_id,
        data=data,
        confidence=confidence,
        prompt_version=prompt_version,
        llm_call_id=llm_call_id,
        generation=generation,
        created_by_user_id=None,
    )
    summary = summarize(doc_type, data)
    await documents.set_current_extraction(
        session,
        scope,
        document_id,
        extraction_id=extraction.id,
        vendor_name=summary.vendor_name,
        document_date=summary.document_date,
        total_amount=summary.total_amount,
        currency=summary.currency,
    )
    return extraction


async def get_current(session: AsyncSession, scope: WorkspaceScope, document_id: str) -> Extraction:
    document = await documents.get_document(session, scope, document_id)
    if document.current_extraction_id is None:
        raise NotFoundError()
    extraction = await repository.get_by_id(session, scope, document.current_extraction_id)
    if extraction is None:
        raise NotFoundError()
    return extraction
