"""Review endpoints (F7 plan §1): save corrections, approve, metrics."""

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks
from fastapi.exceptions import RequestValidationError

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.documents.routes import with_issue_counts
from app.documents.schemas import Document
from app.events.dependencies import EventsDep, JobWakerDep
from app.extractions.routes import to_extraction
from app.extractions.schemas import Extraction
from app.review import service
from app.review.schemas import ApproveRequest, ReviewMetrics, SaveCorrections
from app.storage.dependencies import ClockDep

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["review"])

# "Today" for the date checks: the latest calendar date anywhere, as in the F6 step.
LATEST_OFFSET_HOURS = 14


def _invalid(exc: service.InvalidDataError) -> RequestValidationError:
    return RequestValidationError(
        [
            {"loc": ("body", "data", *path.split(".")), "msg": message, "type": "value_error"}
            for path, message in exc.problems
        ]
    )


@router.put(
    "/documents/{document_id}/extraction", responses=problem_responses(401, 404, 409, 422, 503)
)
async def save_corrections(
    document_id: str,
    body: SaveCorrections,
    *,
    scope: WorkspaceScopeDep,
    session: DbSession,
    clock: ClockDep,
    background: BackgroundTasks,
    wake_worker: JobWakerDep,
) -> Extraction:
    """Save the reviewer's corrections as a new version (AC4). 409 when the document changed
    since `base_version` (AC6); no new version when nothing changed."""
    try:
        saved = await service.save_corrections(
            session,
            scope,
            document_id,
            base_version=body.base_version,
            data=body.data,
            today=_today(clock),
        )
    except service.InvalidDataError as exc:
        raise _invalid(exc) from None
    if saved.changed:
        background.add_task(wake_worker)  # the new version's search embedding (F8)
    return to_extraction(saved.extraction)


@router.post(
    "/documents/{document_id}/approve", responses=problem_responses(401, 404, 409, 422, 503)
)
async def approve_document(
    document_id: str,
    body: ApproveRequest,
    *,
    scope: WorkspaceScopeDep,
    session: DbSession,
    clock: ClockDep,
    background: BackgroundTasks,
    events: EventsDep,
    wake_worker: JobWakerDep,
) -> Document:
    """Approve the document, saving `data` first if given (AC5)."""
    try:
        document, event = await service.approve(
            session,
            scope,
            document_id,
            version=body.version,
            data=body.data,
            accept_errors=body.accept_errors,
            today=_today(clock),
        )
    except service.InvalidDataError as exc:
        raise _invalid(exc) from None
    background.add_task(events.publish, event)
    background.add_task(wake_worker)  # corrections saved here need embedding (F8)
    [approved] = await with_issue_counts(session, scope, [document])
    return approved


@router.get("/metrics/review", responses=problem_responses(401, 404, 503))
async def get_review_metrics(scope: WorkspaceScopeDep, session: DbSession) -> ReviewMetrics:
    """How many approved documents needed no corrections (AC8)."""
    metrics = await service.review_metrics(session, scope)
    return ReviewMetrics(
        approved=metrics.approved,
        approved_without_edits=metrics.approved_without_edits,
        approved_by_agent=metrics.approved_by_agent,
        approved_without_edits_rate=metrics.approved_without_edits / metrics.approved
        if metrics.approved
        else None,
    )


def _today(clock: ClockDep) -> date:
    return (clock.now() + timedelta(hours=LATEST_OFFSET_HOURS)).date()
