"""FastAPI dependencies for authentication (F1 plan §4)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.errors import UnauthenticatedError
from app.auth.verifier import TokenVerifier, VerifiedClaims
from app.core.db import DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.tenancy import WorkspaceScope
from app.identity import service as identity_service
from app.identity.service import CurrentUser

log = get_logger(__name__)

# auto_error=False: we raise our own problem+json 401 instead of FastAPI's default 403.
# Declaring it also documents the `bearerAuth` scheme in openapi.json.
_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth", bearerFormat="JWT")


def get_token_verifier(request: Request) -> TokenVerifier:
    """Indirection so tests can swap in a verifier with local keys."""
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


async def get_verified_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> VerifiedClaims:
    try:
        if credentials is None or not credentials.credentials.strip():
            raise UnauthenticatedError("missing bearer token")
        return await verifier.verify(credentials.credentials)
    except UnauthenticatedError as exc:
        # The reason is logged, never returned: it would help an attacker probe tokens.
        log.info("authentication_failed", reason=exc.reason)
        raise


async def get_current_user(
    claims: Annotated[VerifiedClaims, Depends(get_verified_claims)], session: DbSession
) -> CurrentUser:
    """The authenticated caller, provisioned on first sight (F1 AC5)."""
    current_user = await identity_service.provision_or_load(session, claims)
    structlog.contextvars.bind_contextvars(user_id=str(current_user.id))
    return current_user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_workspace_member(
    workspace_id: str, current_user: CurrentUserDep, session: DbSession
) -> WorkspaceScope:
    """Resolve `{workspace_id}` from the path into a WorkspaceScope, or 404.

    Malformed IDs, unknown IDs and workspaces the caller isn't in all produce the same
    404, so responses never reveal whether a workspace exists (AC15). That is also why the
    path parameter is a plain string: a UUID type would turn malformed IDs into a 422.
    """
    try:
        parsed_id = uuid.UUID(workspace_id)
    except ValueError:
        raise NotFoundError() from None
    role = await identity_service.get_member_role(
        session, workspace_id=parsed_id, user_id=current_user.id
    )
    if role is None:
        raise NotFoundError()
    structlog.contextvars.bind_contextvars(workspace_id=str(parsed_id))
    return WorkspaceScope(workspace_id=parsed_id, user_id=current_user.id, role=role)


WorkspaceScopeDep = Annotated[WorkspaceScope, Depends(require_workspace_member)]


def require_role(*roles: str) -> Callable[[WorkspaceScope], Awaitable[WorkspaceScope]]:
    """A member check plus a role check. Membership is resolved first, so non-members
    get 404 and never learn that a role would have been needed (AC15, AC17)."""

    async def scope_with_role(scope: WorkspaceScopeDep) -> WorkspaceScope:
        if scope.role not in roles:
            raise ForbiddenError()
        return scope

    return scope_with_role


AdminScopeDep = Annotated[WorkspaceScope, Depends(require_role("admin"))]
