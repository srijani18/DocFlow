"""Upload and document rules (F2). Routes stay thin; other modules call this facade."""

import base64
import json
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import WorkspaceScope
from app.documents import repository
from app.documents.models import PROCESSING_STATUSES, Document, DocumentStatus, Upload
from app.jobs import service as jobs
from app.storage.client import SignedUpload, SignedUrl, Storage

# A Supabase signed upload token lasts 2 hours, so an upload can't outlive it (spec D3).
UPLOAD_TTL = timedelta(hours=2)
FILE_URL_TTL_SECONDS = 300  # spec D4
INITIAL_STATUS = DocumentStatus.UPLOADED
WORKER_ROLE = "worker"


class UploadIncompleteError(AppError):
    status = 409
    type_slug = "upload-incomplete"
    title = "The file hasn't been uploaded"


class NotRetryableError(AppError):
    status = 409
    type_slug = "not-retryable"
    title = "Only failed documents can be retried"


class StatusConflictError(Exception):
    """The document isn't in the status a transition expected (another run moved it)."""


@dataclass(frozen=True)
class StatusEvent:
    """A committed status change, for live updates (F3 AC9). Publish only after commit."""

    workspace_id: uuid.UUID
    document_id: uuid.UUID
    status: str
    failure_reason: str | None
    changed_at: datetime


@dataclass(frozen=True)
class NewUpload:
    upload: Upload
    signed: SignedUpload


def created_event(document: Document) -> StatusEvent:
    return StatusEvent(
        workspace_id=document.workspace_id,
        document_id=document.id,
        status=document.status,
        failure_reason=None,
        changed_at=document.status_changed_at,
    )


def storage_path(scope: WorkspaceScope, upload_id: uuid.UUID) -> str:
    """Always built by the server, so a client can never name another workspace's path."""
    return f"{scope.workspace_id}/{upload_id}"


def _parse_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError() from None


async def start_upload(
    session: AsyncSession,
    storage: Storage,
    clock: Clock,
    scope: WorkspaceScope,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
) -> NewUpload | Document:
    """A ticket for a new upload, or the existing document with the same content (AC3)."""
    existing = await repository.find_document_by_sha256(session, scope, sha256)
    if existing is not None:
        return existing
    upload = await repository.insert_upload(
        session,
        scope,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        expires_at=clock.now() + UPLOAD_TTL,
    )
    signed = await storage.create_signed_upload(storage_path(scope, upload.id))
    return NewUpload(upload=upload, signed=signed)


async def complete_upload(
    session: AsyncSession, storage: Storage, clock: Clock, scope: WorkspaceScope, upload_id: str
) -> tuple[Document, bool]:
    """The upload's document, and whether this call created it.

    Repeated completions return the same document (AC5). Two uploads of the same content
    settle on one document through the (workspace_id, sha256) unique index (AC3).
    """
    upload = await repository.lock_upload(session, scope, _parse_id(upload_id))
    if upload is None:
        raise NotFoundError()
    if upload.document_id is not None:
        document = await repository.get_document(session, scope, upload.document_id)
        if document is not None:
            return document, False
    if upload.expires_at <= clock.now():
        raise NotFoundError()

    path = storage_path(scope, upload.id)
    info = await storage.object_info(path)
    if info is None or info.size_bytes != upload.size_bytes:
        raise UploadIncompleteError(
            "The file is missing from storage or its size differs from what was declared."
        )

    document = await repository.insert_document_if_new(
        session, scope, upload, storage_path=path, status=INITIAL_STATUS
    )
    created = document is not None
    if document is None:
        document = await repository.find_document_by_sha256(session, scope, upload.sha256)
        if document is None:  # the unique index guarantees one exists; defensive only
            raise UploadIncompleteError()
    else:
        await repository.insert_event(
            session,
            scope,
            document_id=document.id,
            from_status=None,
            to_status=document.status,
            job_id=None,
            detail=None,
        )
        # The document and its job commit together (ADR-0001, F3 AC1).
        await jobs.enqueue_document_processing(
            session, scope, document_id=document.id, generation=document.processing_generation
        )
    await repository.mark_upload_completed(session, scope, upload.id, document.id)
    return document, created


def encode_cursor(document: Document) -> str:
    raw = json.dumps([document.created_at.isoformat(), str(document.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Raises ValueError for anything that isn't a cursor we issued."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, document_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(created_at), uuid.UUID(document_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid cursor") from exc


async def list_documents(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    before: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> tuple[list[Document], str | None]:
    rows = await repository.list_documents(session, scope, before=before, limit=limit + 1)
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]) if len(rows) > limit else None
    return page, next_cursor


async def get_document(session: AsyncSession, scope: WorkspaceScope, document_id: str) -> Document:
    document = await repository.get_document(session, scope, _parse_id(document_id))
    if document is None:
        raise NotFoundError()
    return document


async def create_file_url(
    session: AsyncSession, storage: Storage, scope: WorkspaceScope, document_id: str
) -> SignedUrl:
    document = await get_document(session, scope, document_id)
    return await storage.create_signed_url(document.storage_path, ttl_seconds=FILE_URL_TTL_SECONDS)


async def transition(
    session: AsyncSession,
    scope: WorkspaceScope,
    document_id: uuid.UUID,
    *,
    expected: Collection[str],
    to: DocumentStatus,
    failure_reason: str | None = None,
    job_id: uuid.UUID | None = None,
    detail: str | None = None,
    bump_generation: bool = False,
) -> tuple[Document, StatusEvent]:
    """The only writer of `documents.status` (F3 plan §3). Locks the row, checks the current
    status, updates it and records the event, all in the caller's transaction (AC2)."""
    current = await repository.lock_document(session, scope, document_id)
    if current is None:
        raise NotFoundError()
    from_status = current.status
    if from_status not in expected:
        raise StatusConflictError(f"{document_id} is {from_status}, expected one of {expected}")
    document = await repository.set_status(
        session,
        scope,
        document_id,
        status=to,
        failure_reason=failure_reason,
        bump_generation=bump_generation,
    )
    await repository.insert_event(
        session,
        scope,
        document_id=document_id,
        from_status=from_status,
        to_status=to,
        job_id=job_id,
        detail=detail,
    )
    event = StatusEvent(
        workspace_id=scope.workspace_id,
        document_id=document_id,
        status=to,
        failure_reason=failure_reason,
        changed_at=document.status_changed_at,
    )
    return document, event


async def fail(
    session: AsyncSession,
    scope: WorkspaceScope,
    document_id: uuid.UUID,
    *,
    reason: str,
    job_id: uuid.UUID | None,
    detail: str | None,
) -> StatusEvent | None:
    """Mark a document FAILED from whichever processing step it reached (F3 AC3, AC4)."""
    try:
        _, event = await transition(
            session,
            scope,
            document_id,
            expected=PROCESSING_STATUSES,
            to=DocumentStatus.FAILED,
            failure_reason=reason,
            job_id=job_id,
            detail=detail,
        )
    except StatusConflictError:
        return None  # already finished or failed by another run
    return event


async def retry_document(
    session: AsyncSession, scope: WorkspaceScope, document_id: str
) -> tuple[Document, StatusEvent]:
    """Queue a FAILED document again with a fresh set of attempts (F3 AC8)."""
    try:
        document, event = await transition(
            session,
            scope,
            _parse_id(document_id),
            expected=[DocumentStatus.FAILED],
            to=DocumentStatus.UPLOADED,
            bump_generation=True,
            detail="retry",
        )
    except StatusConflictError:
        raise NotRetryableError() from None
    await jobs.enqueue_document_processing(
        session, scope, document_id=document.id, generation=document.processing_generation
    )
    return document, event


async def load_for_job(
    session: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[WorkspaceScope, Document] | None:
    """The scope a job runs in: the document's workspace, acting for its uploader."""
    document = await repository.get_document_for_job(
        session, workspace_id=workspace_id, document_id=document_id
    )
    if document is None:
        return None
    scope = WorkspaceScope(
        workspace_id=workspace_id, user_id=document.created_by_user_id, role=WORKER_ROLE
    )
    return scope, document


async def set_classification(
    session: AsyncSession,
    scope: WorkspaceScope,
    document_id: uuid.UUID,
    *,
    doc_type: str,
    confidence: float,
) -> None:
    await repository.set_classification(
        session, scope, document_id, doc_type=doc_type, confidence=confidence
    )
