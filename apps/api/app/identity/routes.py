"""Identity endpoints (F1 plan §2). Thin: parse, call the service, shape the response."""

from fastapi import APIRouter

from app.auth.dependencies import AdminScopeDep, CurrentUserDep, WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.identity import service
from app.identity.models import Workspace as WorkspaceRow
from app.identity.schemas import (
    Me,
    Membership,
    Role,
    User,
    Workspace,
    WorkspaceSummary,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/v1", tags=["identity"])


@router.get("/me", responses=problem_responses(401, 503))
async def get_me(current_user: CurrentUserDep, session: DbSession) -> Me:
    """The signed-in user and their workspaces. Provisions the user on first call (AC5)."""
    memberships = await service.list_memberships(session, current_user.id)
    return Me(
        user=User(
            id=current_user.id, email=current_user.email, display_name=current_user.display_name
        ),
        memberships=[
            Membership(
                workspace=WorkspaceSummary(id=row.workspace_id, name=row.workspace_name),
                role=Role(row.role),
            )
            for row in memberships
        ],
    )


@router.get("/workspaces/{workspace_id}", responses=problem_responses(401, 404, 503))
async def get_workspace(scope: WorkspaceScopeDep, session: DbSession) -> Workspace:
    """A workspace the caller belongs to. Anything else is 404 (AC15)."""
    workspace = await service.get_workspace(session, scope)
    return _workspace_response(workspace, scope.role)


@router.patch("/workspaces/{workspace_id}", responses=problem_responses(401, 403, 404, 422, 503))
async def update_workspace(
    update: WorkspaceUpdate, scope: AdminScopeDep, session: DbSession
) -> Workspace:
    """Rename a workspace. Admins only (AC16, AC17)."""
    workspace = await service.rename_workspace(session, scope, update.name)
    return _workspace_response(workspace, scope.role)


def _workspace_response(workspace: WorkspaceRow, role: str) -> Workspace:
    return Workspace(
        id=workspace.id, name=workspace.name, role=Role(role), created_at=workspace.created_at
    )
