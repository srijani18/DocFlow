"""Extraction endpoint (F5 plan §2)."""

from fastapi import APIRouter

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.extractions import service
from app.extractions.ordering import order_like_schema
from app.extractions.schemas import Extraction
from app.schemas_registry import bundle

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["extractions"])


@router.get("/documents/{document_id}/extraction", responses=problem_responses(401, 404, 503))
async def get_current_extraction(
    document_id: str, scope: WorkspaceScopeDep, session: DbSession
) -> Extraction:
    """The document's current extraction; 404 until one exists (F5 AC6)."""
    row = await service.get_current(session, scope, document_id)
    extraction = Extraction.model_validate(row, from_attributes=True)
    extraction.data = order_like_schema(row.data, bundle(row.schema_id))
    return extraction
