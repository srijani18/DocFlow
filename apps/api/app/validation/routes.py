"""Validation issues endpoint (F6 plan §4)."""

from fastapi import APIRouter

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.validation import service
from app.validation.schemas import ValidationIssue, ValidationIssueList

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["validation"])


@router.get("/documents/{document_id}/issues", responses=problem_responses(401, 404, 503))
async def list_issues(
    document_id: str, scope: WorkspaceScopeDep, session: DbSession
) -> ValidationIssueList:
    """Issues found on the document's current extraction (AC2); 404 until one exists."""
    rows = await service.list_current_issues(session, scope, document_id)
    return ValidationIssueList(
        items=[ValidationIssue.model_validate(row, from_attributes=True) for row in rows]
    )
