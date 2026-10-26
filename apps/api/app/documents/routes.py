"""Upload and document endpoints (F2 plan §2). Thin: parse, call the service, shape."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.core.tenancy import WorkspaceScope
from app.documents import service
from app.documents.models import PROCESSING_STATUSES
from app.documents.models import Document as DocumentRow
from app.documents.schemas import (
    Document,
    DocumentPage,
    FileUrl,
    IssueCounts,
    UploadDuplicate,
    UploadStart,
    UploadStartResult,
    UploadTicket,
)
from app.events.dependencies import EventsDep, JobWakerDep
from app.storage.dependencies import ClockDep, StorageDep
from app.validation import service as validation

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["documents"])


def to_document(row: DocumentRow) -> Document:
    return Document.model_validate(row, from_attributes=True)


async def with_issue_counts(
    session: AsyncSession, scope: WorkspaceScope, rows: list[DocumentRow]
) -> list[Document]:
    """Documents with their open issue counts, one query for the whole page (F6)."""
    # While a document is (re)processing, its old counts would be stale.
    validated = {
        row.id: row.current_extraction_id
        for row in rows
        if row.current_extraction_id is not None and row.status not in PROCESSING_STATUSES
    }
    counts = await validation.open_issue_counts(session, scope, list(validated.values()))
    documents = []
    for row in rows:
        document = to_document(row)
        if (extraction_id := validated.get(row.id)) is not None:
            document.issue_counts = IssueCounts(**counts[extraction_id])
        documents.append(document)
    return documents


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": UploadDuplicate, "description": "Duplicate: nothing to upload (AC3)"},
        **problem_responses(401, 404, 422, 503),
    },
)
async def start_upload(
    start: UploadStart,
    *,
    scope: WorkspaceScopeDep,
    session: DbSession,
    storage: StorageDep,
    clock: ClockDep,
    response: Response,
) -> UploadStartResult:
    """Start an upload: returns a signed upload ticket, or the existing duplicate."""
    result = await service.start_upload(
        session,
        storage,
        clock,
        scope,
        filename=start.filename,
        content_type=start.content_type,
        size_bytes=start.size_bytes,
        sha256=start.sha256,
    )
    if isinstance(result, service.NewUpload):
        return UploadTicket(
            upload_id=result.upload.id,
            bucket=result.signed.bucket,
            path=result.signed.path,
            token=result.signed.token,
            expires_at=result.upload.expires_at,
        )
    response.status_code = status.HTTP_200_OK
    return UploadDuplicate(document=to_document(result))


@router.post(
    "/uploads/{upload_id}/complete",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": Document, "description": "Already completed, or a duplicate"},
        **problem_responses(401, 404, 409, 503),
    },
)
async def complete_upload(
    upload_id: str,
    *,
    scope: WorkspaceScopeDep,
    session: DbSession,
    storage: StorageDep,
    clock: ClockDep,
    response: Response,
    background: BackgroundTasks,
    events: EventsDep,
    wake_worker: JobWakerDep,
) -> Document:
    """Record the uploaded file as a document once it is in storage (AC1, AC4, AC5), and
    queue its processing (F3 AC1)."""
    document, created = await service.complete_upload(session, storage, clock, scope, upload_id)
    if not created:
        response.status_code = status.HTTP_200_OK
        return to_document(document)
    # Background tasks run after the response, so after the commit: the worker and other
    # tabs never see a job or document that isn't committed yet.
    background.add_task(wake_worker)
    background.add_task(events.publish, service.created_event(document))
    return to_document(document)


@router.get("/documents", responses=problem_responses(401, 404, 422, 503))
async def list_documents(
    scope: WorkspaceScopeDep,
    session: DbSession,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DocumentPage:
    """The workspace's documents, newest first (AC8)."""
    try:
        before = service.decode_cursor(cursor) if cursor else None
    except ValueError:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "Invalid cursor", "type": "value_error"}]
        ) from None
    rows, next_cursor = await service.list_documents(session, scope, before=before, limit=limit)
    return DocumentPage(
        items=await with_issue_counts(session, scope, rows), next_cursor=next_cursor
    )


@router.get("/documents/{document_id}", responses=problem_responses(401, 404, 503))
async def get_document(document_id: str, scope: WorkspaceScopeDep, session: DbSession) -> Document:
    row = await service.get_document(session, scope, document_id)
    [document] = await with_issue_counts(session, scope, [row])
    return document


@router.post("/documents/{document_id}/file-url", responses=problem_responses(401, 404, 503))
async def create_document_file_url(
    document_id: str, scope: WorkspaceScopeDep, session: DbSession, storage: StorageDep
) -> FileUrl:
    """A link to the original file, valid for 5 minutes (AC9)."""
    signed = await service.create_file_url(session, storage, scope, document_id)
    return FileUrl(url=signed.url, expires_at=signed.expires_at)


@router.post(
    "/documents/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(401, 404, 409, 503),
)
async def retry_document(
    document_id: str,
    *,
    scope: WorkspaceScopeDep,
    session: DbSession,
    background: BackgroundTasks,
    events: EventsDep,
    wake_worker: JobWakerDep,
) -> Document:
    """Process a FAILED document again with a fresh set of attempts (F3 AC8)."""
    document, event = await service.retry_document(session, scope, document_id)
    background.add_task(wake_worker)
    background.add_task(events.publish, event)
    return to_document(document)
