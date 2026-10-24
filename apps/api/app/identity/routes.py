"""Identity endpoints (F1 plan §2). Thin: parse, call the service, shape the response."""

from fastapi import APIRouter

from app.auth.dependencies import CurrentUserDep
from app.core.db import DbSession
from app.core.errors import problem_responses
from app.identity import service
from app.identity.schemas import Me, Membership, Role, User, WorkspaceSummary

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
