"""Human review: save corrections and approve (F7). Other modules use this facade."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents
from app.documents.models import Document, DocumentStatus
from app.extractions import envelope
from app.extractions import service as extractions
from app.extractions.models import Extraction
from app.review import repository
from app.review.diff import diff, exact
from app.schemas_registry import validation_errors
from app.validation import service as validation
from app.validation.checks import all_checks

HUMAN_CONFIDENCE = Decimal(1)  # a reviewer has looked at the field


class VersionConflictError(AppError):
    status = 409
    type_slug = "version-conflict"
    title = "This document changed since you opened it"


class NotReviewableError(AppError):
    status = 409
    type_slug = "not-reviewable"
    title = "Only documents waiting for review can be changed or approved"


class OpenErrorsError(AppError):
    status = 409
    type_slug = "open-errors"
    title = "This document has unresolved errors"


@dataclass
class InvalidDataError(Exception):
    """The corrected data doesn't fit the schema: (path, message) pairs."""

    problems: list[tuple[str, str]]


@dataclass
class Saved:
    document: Document
    extraction: Extraction
    changed: bool


async def _reviewable(
    session: AsyncSession, scope: WorkspaceScope, document_id: str, base_version: int
) -> tuple[Document, Extraction]:
    document = await documents.lock_document(session, scope, document_id)
    if document.status != DocumentStatus.NEEDS_REVIEW or document.current_extraction_id is None:
        raise NotReviewableError()
    current = await extractions.get_current(session, scope, document_id)
    if current.version != base_version:
        raise VersionConflictError(
            f"You opened version {base_version}; the current version is {current.version}."
        )
    return document, current


async def _save(
    session: AsyncSession,
    scope: WorkspaceScope,
    document: Document,
    current: Extraction,
    data: dict[str, Any],
    *,
    today: date,
) -> tuple[Extraction, bool]:
    data = exact(data)
    problems = validation_errors(current.schema_id, data)
    if problems:
        raise InvalidDataError([tuple(p.split(": ", 1)) for p in problems])  # type: ignore[misc]
    before = await extractions.get_exact_data(session, scope, current.id)
    changes = diff(before, data)
    if not changes:
        return current, False
    confidence = {
        path: score for path, score in current.confidence.items() if envelope.has_path(data, path)
    }
    confidence.update({c.path: HUMAN_CONFIDENCE for c in changes if c.new is not None})
    doc_type = envelope.DOC_TYPE_BY_SCHEMA[current.schema_id]
    saved = await extractions.record_human_version(
        session,
        scope,
        document_id=document.id,
        doc_type=doc_type,
        schema_id=current.schema_id,
        data=data,
        confidence=confidence,
        generation=document.processing_generation,
    )
    await repository.insert_corrections(
        session, scope, document_id=document.id, extraction_id=saved.id, changes=changes
    )
    # The F6 checks (no model calls) on the new version, so the problem list stays current.
    issues = await all_checks(
        doc_type,
        data,
        today=today,
        lookups=validation.lookups_in(session, scope, document_id=document.id, doc_type=doc_type),
    )
    await validation.record_issues(
        session, scope, document_id=document.id, extraction_id=saved.id, remaining=issues, fixed=[]
    )
    return saved, True


async def save_corrections(
    session: AsyncSession,
    scope: WorkspaceScope,
    document_id: str,
    *,
    base_version: int,
    data: dict[str, Any],
    today: date,
) -> Saved:
    """Store the reviewer's corrected data as a new version (AC4), unless nothing changed."""
    document, current = await _reviewable(session, scope, document_id, base_version)
    extraction, changed = await _save(session, scope, document, current, data, today=today)
    return Saved(document, extraction, changed)


async def approve(
    session: AsyncSession,
    scope: WorkspaceScope,
    document_id: str,
    *,
    version: int,
    data: dict[str, Any] | None,
    accept_errors: bool,
    today: date,
) -> tuple[Document, documents.StatusEvent]:
    """Save any changes, then approve the resulting version (AC5). Open errors need
    `accept_errors` ("Approve anyway"); warnings don't."""
    document, current = await _reviewable(session, scope, document_id, version)
    if data is not None:
        current, _ = await _save(session, scope, document, current, data, today=today)
    if not accept_errors and (errors := await validation.open_errors(session, scope, current.id)):
        raise OpenErrorsError("; ".join(issue.message for issue in errors))
    return await documents.approve(
        session,
        scope,
        document.id,
        expected=[DocumentStatus.NEEDS_REVIEW],
        by_user_id=scope.user_id,
        extraction_id=current.id,
    )


@dataclass(frozen=True)
class ReviewMetrics:
    approved: int
    approved_without_edits: int
    approved_by_agent: int


async def review_metrics(session: AsyncSession, scope: WorkspaceScope) -> ReviewMetrics:
    approved, edited, by_agent = await repository.approval_counts(session, scope)
    return ReviewMetrics(approved, approved - edited, by_agent)


@dataclass(frozen=True)
class ApprovedDocument:
    document: Document
    schema_id: str
    data: dict[str, Any]
    corrections: int


async def approved_by_people(
    session: AsyncSession, scope: WorkspaceScope
) -> list[ApprovedDocument]:
    """What a person checked and approved: verified truth for evals (AC9)."""
    return [
        ApprovedDocument(
            document=document,
            schema_id=extraction.schema_id,
            data=await extractions.get_exact_data(session, scope, extraction.id),
            corrections=corrections,
        )
        for document, extraction, corrections in await repository.approved_by_people(session, scope)
    ]
