"""Extraction endpoint (F5 plan §2)."""

from typing import Any

from fastapi import APIRouter

from app.auth.dependencies import CurrentUserDep, WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import NotFoundError, problem_responses
from app.extractions import service
from app.extractions.models import Extraction as ExtractionRow
from app.extractions.ordering import order_like_schema
from app.extractions.schemas import Extraction
from app.schemas_registry import bundle, schema_ids

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["extractions"])


@router.get("/documents/{document_id}/extraction", responses=problem_responses(401, 404, 503))
async def get_current_extraction(
    document_id: str, scope: WorkspaceScopeDep, session: DbSession
) -> Extraction:
    """The document's current extraction; 404 until one exists (F5 AC6)."""
    return to_extraction(await service.get_current(session, scope, document_id))


def to_extraction(row: ExtractionRow) -> Extraction:
    extraction = Extraction.model_validate(row, from_attributes=True)
    extraction.data = order_like_schema(row.data, bundle(row.schema_id))
    return extraction


schema_router = APIRouter(prefix="/v1/schemas", tags=["extractions"])


@schema_router.get("/{schema_id:path}", responses=problem_responses(401, 404))
async def get_schema(schema_id: str, _user: CurrentUserDep) -> dict[str, Any]:
    """A bundled document schema (no tenant data), for the review form (F7 plan §3)."""
    if schema_id not in schema_ids():
        raise NotFoundError()
    return bundle(schema_id)
