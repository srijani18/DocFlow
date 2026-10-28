"""Access tokens for AI assistants (F12 plan §3). Members manage their own; admins see and
revoke all of the workspace's."""

from fastapi import APIRouter, Response, status

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.mcp import tokens
from app.mcp.schemas import ApiToken, ApiTokenCreate, ApiTokenCreated
from app.storage.dependencies import ClockDep

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/api-tokens", tags=["api-tokens"])


def _to_schema(row: tokens.TokenRow) -> ApiToken:
    token = row.token
    return ApiToken(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        created_by=row.creator_email,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        active=row.active,
    )


@router.get("", responses=problem_responses(401, 404, 503))
async def list_api_tokens(
    scope: WorkspaceScopeDep, session: DbSession, clock: ClockDep
) -> list[ApiToken]:
    """Your tokens, or every token in the workspace for admins (AC3). Never the tokens
    themselves."""
    return [_to_schema(row) for row in await tokens.list_tokens(session, scope, now=clock.now())]


@router.post(
    "", status_code=status.HTTP_201_CREATED, responses=problem_responses(401, 404, 422, 503)
)
async def create_api_token(
    body: ApiTokenCreate, scope: WorkspaceScopeDep, session: DbSession, clock: ClockDep
) -> ApiTokenCreated:
    """A new token for your AI assistant. The `token` is in this response only (AC1)."""
    row, token = await tokens.create_token(
        session, scope, name=body.name, expires_in_days=body.expires_in_days, now=clock.now()
    )
    listed = tokens.TokenRow(token=row, creator_email=None, active=True)
    return ApiTokenCreated(**_to_schema(listed).model_dump(), token=token)


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 404, 503),
)
async def revoke_api_token(
    token_id: str, scope: WorkspaceScopeDep, session: DbSession, clock: ClockDep
) -> Response:
    """Revoke a token; it stops working on its next request (AC3)."""
    await tokens.revoke_token(session, scope, token_id, now=clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
