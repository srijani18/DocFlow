"""Authentication errors (F1 plan §7). Each maps to a problem+json response via AppError."""

from app.core.errors import AppError, ServiceUnavailableError


class UnauthenticatedError(AppError):
    """401. The client-facing detail is always generic; `reason` is for logs only."""

    status = 401
    type_slug = "unauthenticated"
    title = "Authentication required"

    def __init__(self, reason: str) -> None:
        super().__init__(headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
        self.reason = reason


class UnknownSigningKeyError(UnauthenticatedError):
    """The token names a key (`kid`) the identity provider does not publish."""

    def __init__(self, kid: str) -> None:
        super().__init__(f"unknown signing key {kid!r}")


class AuthUnavailableError(ServiceUnavailableError):
    """503: we cannot verify any token because no signing keys could ever be fetched."""

    type_slug = "auth-unavailable"
    title = "Authentication temporarily unavailable"
