"""RFC 9457 problem+json errors (constitution §8.2).

Every error response has the same shape. Raise an `AppError` subclass from any layer;
the handlers in `app.core.error_handlers` turn it into a response. This module has no
web-framework imports, so the worker can share these error types (ADR-0002).
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, ClassVar

from pydantic import BaseModel

PROBLEM_TYPE_BASE = "https://docflow.dev/problems/"
PROBLEM_CONTENT_TYPE = "application/problem+json"


class ProblemFieldError(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    """The body of every error response (OpenAPI documentation only)."""

    type: str
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None
    errors: list[ProblemFieldError] | None = None


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` for a route: document each status as application/problem+json."""
    return {
        status: {
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }


class AppError(Exception):
    """Base for errors that map to a specific problem type."""

    status: ClassVar[int] = 500
    type_slug: ClassVar[str] = "internal"
    title: ClassVar[str] = "Internal server error"

    def __init__(self, detail: str | None = None, *, headers: Mapping[str, str] | None = None):
        super().__init__(detail or self.title)
        self.detail = detail
        self.headers = dict(headers or {})


class NotFoundError(AppError):
    status = 404
    type_slug = "not-found"
    title = "Not found"


class ForbiddenError(AppError):
    status = 403
    type_slug = "forbidden"
    title = "Forbidden"


class ServiceUnavailableError(AppError):
    status = 503
    type_slug = "unavailable"
    title = "Service temporarily unavailable"

    def __init__(self, detail: str | None = None, *, retry_after_seconds: int = 5):
        super().__init__(detail, headers={"Retry-After": str(retry_after_seconds)})


class DatabaseUnavailableError(ServiceUnavailableError):
    type_slug = "database-unavailable"
    title = "Database temporarily unavailable"
