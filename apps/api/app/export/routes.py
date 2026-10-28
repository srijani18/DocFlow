"""Export endpoint (F9 plan §1)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import RateLimiterDep, WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.documents.models import DocType, DocumentStatus
from app.export import service
from app.search.dependencies import QueryEmbedderDep
from app.search.repository import Filters

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["export"])

MEDIA_TYPES = {"csv": "application/zip", "json": "application/json"}
EXTENSIONS = {"csv": "zip", "json": "json"}


@router.get(
    "/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/zip": {}, "application/json": {}},
            "description": "The export file, as an attachment",
        },
        **problem_responses(401, 404, 422, 503),
    },
)
async def export_documents(
    *,
    scope: WorkspaceScopeDep,
    limiter: RateLimiterDep,
    session: DbSession,
    embedder: QueryEmbedderDep,
    format: service.Format = "csv",  # the public parameter name
    include_unapproved: bool = False,
    q: Annotated[str, Query(max_length=200)] = "",
    doc_type: DocType | None = None,
    status: DocumentStatus | None = None,
    vendor: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
) -> StreamingResponse:
    """Approved documents matching the search filters, as a ZIP of two CSV files or as
    JSON (AC1 to AC8). 422 when more than 5,000 documents match."""
    if q.strip():  # embedding the query calls the AI provider (F14 AC9)
        limiter.check("ai", str(scope.user_id))
    selection = await service.select(
        session,
        scope,
        text=q,
        filters=Filters(
            doc_type=doc_type,
            status=status,
            vendor=vendor.strip() if vendor else None,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
        ),
        include_unapproved=include_unapproved,
        embed_query=embedder(scope),
    )
    body = (
        service.csv_zip(session, selection)
        if format == "csv"
        else service.json_array(session, selection)
    )
    filename = f"docflow-export-{datetime.now(UTC):%Y%m%d-%H%M}.{EXTENSIONS[format]}"
    return StreamingResponse(
        body,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
