"""RFC 9457 problem+json errors (constitution §8.2).

Every error response has the same shape. Raise an `AppError` subclass from any layer;
the handlers installed by `install_error_handlers` turn it into a response.
"""

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, ClassVar

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

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


def problem_response(
    *,
    status: int,
    type_slug: str,
    title: str,
    request_id: str | None,
    detail: str | None = None,
    errors: Sequence[Mapping[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"type": PROBLEM_TYPE_BASE + type_slug, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    if request_id:
        body["request_id"] = request_id
    if errors is not None:
        body["errors"] = list(errors)
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_CONTENT_TYPE)


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def _field_name(loc: Sequence[int | str]) -> str:
    # ("body", "name") -> "name"; ("query", "limit") -> "limit"; nested -> "a.b.0".
    parts = list(loc[1:]) if loc and loc[0] in {"body", "query", "path", "header"} else list(loc)
    return ".".join(str(part) for part in parts) or "body"


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # handlers are registered per type; narrows for mypy
        raise exc
    return problem_response(
        status=exc.status,
        type_slug=exc.type_slug,
        title=exc.title,
        detail=exc.detail,
        request_id=_request_id(request),
        headers=exc.headers,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(
        exc, RequestValidationError
    ):  # handlers are registered per type; narrows for mypy
        raise exc
    errors = [
        {"field": _field_name(error.get("loc", ())), "message": str(error.get("msg", "Invalid"))}
        for error in exc.errors()
    ]
    return problem_response(
        status=422,
        type_slug="validation",
        title="Request validation failed",
        request_id=_request_id(request),
        errors=errors,
    )


_HTTP_STATUS_SLUGS = {404: "not-found", 405: "method-not-allowed", 403: "forbidden"}


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(
        exc, StarletteHTTPException
    ):  # handlers are registered per type; narrows for mypy
        raise exc
    status = exc.status_code
    return problem_response(
        status=status,
        type_slug=_HTTP_STATUS_SLUGS.get(status, "http-error"),
        title=HTTPStatus(status).phrase,
        request_id=_request_id(request),
        headers=exc.headers,
    )


async def _handle_database_connection_error(request: Request, exc: Exception) -> JSONResponse:
    # Connection-level failures (pooler restarts, network blips) are transient: answer 503 with
    # Retry-After and let the client retry (F1 AC20), instead of retrying hidden in here.
    structlog.get_logger(__name__).warning("database_unavailable", error_type=type(exc).__name__)
    return await _handle_app_error(request, DatabaseUnavailableError())


def internal_error_response(request_id: str | None) -> JSONResponse:
    """The last-resort 500. Never includes exception text: that goes to the logs only."""
    structlog.get_logger(__name__).exception("unhandled_error")
    return problem_response(
        status=500, type_slug="internal", title="Internal server error", request_id=request_id
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(OperationalError, _handle_database_connection_error)
    app.add_exception_handler(InterfaceError, _handle_database_connection_error)
