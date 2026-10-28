"""Search endpoint (F8 plan §1)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError

from app.auth.dependencies import RateLimiterDep, WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.documents.models import DocType, DocumentStatus
from app.documents.routes import with_issue_counts
from app.search import service
from app.search.dependencies import QueryEmbedderDep
from app.search.repository import Filters
from app.search.schemas import SearchHit, SearchResults

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["search"])


@router.get("/search", responses=problem_responses(401, 404, 422, 503))
async def search_documents(
    *,
    scope: WorkspaceScopeDep,
    limiter: RateLimiterDep,
    session: DbSession,
    embedder: QueryEmbedderDep,
    q: Annotated[str, Query(max_length=200)] = "",
    doc_type: DocType | None = None,
    status: DocumentStatus | None = None,
    vendor: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResults:
    """The workspace's documents matching the text (by keyword and meaning) and filters,
    best first; newest first without text (AC1 to AC5)."""
    try:
        offset = service.decode_cursor(cursor) if cursor else 0
    except ValueError:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "Invalid cursor", "type": "value_error"}]
        ) from None
    if q.strip():  # embedding the query calls the AI provider (F14 AC9)
        limiter.check("ai", str(scope.user_id))
    page = await service.search(
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
        offset=offset,
        limit=limit,
        embed_query=embedder(scope),
    )
    documents = await with_issue_counts(session, scope, [hit.document for hit in page.hits])
    return SearchResults(
        items=[
            SearchHit(document=document, matched=hit.matched, snippet=hit.snippet)
            for document, hit in zip(documents, page.hits, strict=True)
        ],
        next_cursor=service.encode_cursor(page.next_offset) if page.next_offset else None,
        semantic=page.semantic,
    )
