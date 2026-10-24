"""F1-T9: the generated OpenAPI document keeps the contract in F1 plan §2.

The web client is generated from this document, so these are the promises the frontend
relies on: operation IDs, auth, error media types and the response shapes.
"""

from typing import Any

import pytest

from app.main import create_app
from app.openapi import EXPORT_SETTINGS

PROBLEM = "application/problem+json"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return create_app(EXPORT_SETTINGS).openapi()


@pytest.mark.parametrize(
    ("method", "path", "operation_id", "errors"),
    [
        ("get", "/v1/me", "getMe", {"401", "503"}),
        ("get", "/v1/workspaces/{workspace_id}", "getWorkspace", {"401", "404", "503"}),
        (
            "patch",
            "/v1/workspaces/{workspace_id}",
            "updateWorkspace",
            {"401", "403", "404", "422", "503"},
        ),
    ],
)
def test_openapi_matches_f1_contract_operations(
    document: dict[str, Any], method: str, path: str, operation_id: str, errors: set[str]
) -> None:
    operation = document["paths"][path][method]

    assert operation["operationId"] == operation_id
    assert operation["security"] == [{"bearerAuth": []}]
    assert set(operation["responses"]) == {"200"} | errors
    for status in errors:
        content = operation["responses"][status]["content"]
        assert list(content) == [PROBLEM]
        assert content[PROBLEM]["schema"] == {"$ref": "#/components/schemas/Problem"}


def test_workspace_id_is_a_plain_string_so_malformed_ids_can_404(document: dict[str, Any]) -> None:
    for method in ("get", "patch"):
        [parameter] = document["paths"]["/v1/workspaces/{workspace_id}"][method]["parameters"]
        assert (parameter["name"], parameter["in"], parameter["schema"]["type"]) == (
            "workspace_id",
            "path",
            "string",
        )


def test_bearer_auth_scheme(document: dict[str, Any]) -> None:
    assert document["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }


@pytest.mark.parametrize(
    ("schema", "required"),
    [
        ("Me", {"user", "memberships"}),
        ("User", {"id", "email", "display_name"}),
        ("Membership", {"workspace", "role"}),
        ("WorkspaceSummary", {"id", "name"}),
        ("Workspace", {"id", "name", "role", "created_at"}),
        ("WorkspaceUpdate", {"name"}),
        ("Problem", {"type", "title", "status"}),
    ],
)
def test_response_shapes(document: dict[str, Any], schema: str, required: set[str]) -> None:
    assert set(document["components"]["schemas"][schema]["required"]) == required


def test_roles_and_field_rules(document: dict[str, Any]) -> None:
    schemas = document["components"]["schemas"]

    assert schemas["Role"]["enum"] == ["admin", "reviewer"]
    assert schemas["WorkspaceUpdate"]["additionalProperties"] is False
    for name in ("Workspace", "WorkspaceUpdate"):
        field = schemas[name]["properties"]["name"]
        assert (field["minLength"], field["maxLength"]) == (1, 80)
    for nullable in ("email", "display_name"):
        types = {option["type"] for option in schemas["User"]["properties"][nullable]["anyOf"]}
        assert types == {"string", "null"}


def test_no_fastapi_validation_schemas_leak_into_the_contract(document: dict[str, Any]) -> None:
    assert not {"HTTPValidationError", "ValidationError"} & set(document["components"]["schemas"])
