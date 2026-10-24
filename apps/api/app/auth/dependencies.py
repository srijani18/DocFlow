"""FastAPI dependencies for authentication (F1 plan §4)."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.errors import UnauthenticatedError
from app.auth.verifier import TokenVerifier, VerifiedClaims
from app.core.logging import get_logger

log = get_logger(__name__)

# auto_error=False: we raise our own problem+json 401 instead of FastAPI's default 403.
# Declaring it also documents the `bearerAuth` scheme in openapi.json.
_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


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
