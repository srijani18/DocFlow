"""Make the generated OpenAPI document describe our real error format (constitution §8.2).

FastAPI documents 422s with its own `HTTPValidationError` JSON shape, but every error here
is RFC 9457 problem+json. This hook registers the `Problem` schema, rewrites 422s to use it,
and drops 422 from operations that have no body or query parameters (they cannot fail
validation: path IDs are plain strings so that malformed IDs return 404).
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from app.core.errors import PROBLEM_CONTENT_TYPE, Problem, problem_responses

_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def install_problem_openapi(app: FastAPI) -> None:
    generate: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        document = generate()
        schemas = document.setdefault("components", {}).setdefault("schemas", {})
        problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(problem.pop("$defs", {}))
        schemas["Problem"] = problem
        for name in _FASTAPI_VALIDATION_SCHEMAS:
            schemas.pop(name, None)
        for path_item in document.get("paths", {}).values():
            for operation in path_item.values():
                _fix_validation_response(operation)
        app.openapi_schema = document
        return document

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented override hook


def _fix_validation_response(operation: dict[str, Any]) -> None:
    responses = operation.get("responses", {})
    if "422" not in responses:
        return
    can_fail_validation = "requestBody" in operation or any(
        parameter.get("in") == "query" for parameter in operation.get("parameters", [])
    )
    if not can_fail_validation:
        del responses["422"]
        return
    content = responses["422"].get("content", {})
    if PROBLEM_CONTENT_TYPE not in content:
        responses["422"] = problem_responses(422)[422]
