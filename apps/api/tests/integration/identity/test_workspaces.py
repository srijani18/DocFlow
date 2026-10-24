import uuid
from typing import Any

import httpx
import pytest

from tests.support.identity import TwoWorkspaces, UserRef
from tests.support.jwt import bearer


def as_user(user: UserRef) -> dict[str, str]:
    return bearer(sub=user.auth_subject, email=user.email)


def _without_request_id(response: httpx.Response) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    body.pop("request_id", None)
    return body


@pytest.mark.parametrize(("member", "role"), [("a_admin", "admin"), ("a_reviewer", "reviewer")])
async def test_ac14_member_gets_workspace_with_role(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, member: str, role: str
) -> None:
    w = two_workspaces
    response = await db_client.get(f"/v1/workspaces/{w.a.id}", headers=as_user(getattr(w, member)))

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["name"], body["role"]) == (str(w.a.id), "Workspace A", role)
    assert body["created_at"]


async def test_ac15_non_member_and_unknown_and_malformed_ids_get_identical_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    ids = [w.b.id, uuid.UUID(int=0), uuid.uuid4(), "not-a-uuid", "1' OR '1'='1"]

    responses = [
        await db_client.get(f"/v1/workspaces/{workspace_id}", headers=as_user(w.a_admin))
        for workspace_id in ids
    ]

    assert {response.status_code for response in responses} == {404}
    bodies = [_without_request_id(response) for response in responses]
    assert all(body == bodies[0] for body in bodies)
    assert bodies[0]["type"].endswith("/not-found")
    assert "detail" not in bodies[0]


async def test_ac19_member_of_a_cannot_read_b(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    for user in (w.a_admin, w.a_reviewer):
        response = await db_client.get(f"/v1/workspaces/{w.b.id}", headers=as_user(user))
        assert response.status_code == 404
        assert "Workspace B" not in response.text

    own = await db_client.get(f"/v1/workspaces/{w.b.id}", headers=as_user(w.b_admin))
    assert own.status_code == 200


async def test_ac11_workspace_requires_a_token(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    response = await db_client.get(f"/v1/workspaces/{two_workspaces.a.id}")

    assert response.status_code == 401


async def _name_of(db_client: httpx.AsyncClient, w: TwoWorkspaces) -> str:
    response = await db_client.get(f"/v1/workspaces/{w.a.id}", headers=as_user(w.a_admin))
    name: str = response.json()["name"]
    return name


@pytest.mark.parametrize(
    ("submitted", "saved"),
    [("  Acme Finance  ", "Acme Finance"), ("x" * 80, "x" * 80), ("名" * 80, "名" * 80)],
    ids=["trimmed", "80-ascii", "80-cjk"],
)
async def test_ac16_admin_renames_trimmed(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, submitted: str, saved: str
) -> None:
    w = two_workspaces
    response = await db_client.patch(
        f"/v1/workspaces/{w.a.id}", json={"name": submitted}, headers=as_user(w.a_admin)
    )

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["role"]) == (saved, "admin")
    assert await _name_of(db_client, w) == saved


async def test_ac17_reviewer_forbidden_name_unchanged(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    response = await db_client.patch(
        f"/v1/workspaces/{w.a.id}", json={"name": "Hijacked"}, headers=as_user(w.a_reviewer)
    )

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/forbidden")
    assert await _name_of(db_client, w) == "Workspace A"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "    "}, "name"),
        ({"name": "x" * 81}, "name"),
        ({}, "name"),
        ({"name": 42}, "name"),
        ({"name": "Fine", "nickname": "extra"}, "nickname"),
    ],
    ids=["empty", "whitespace", "81-chars", "missing", "not-a-string", "unknown-field"],
)
async def test_ac18_invalid_names_rejected_with_field_error(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, body: dict[str, Any], field: str
) -> None:
    w = two_workspaces
    response = await db_client.patch(
        f"/v1/workspaces/{w.a.id}", json=body, headers=as_user(w.a_admin)
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [error["field"] for error in response.json()["errors"]] == [field]
    assert await _name_of(db_client, w) == "Workspace A"


@pytest.mark.parametrize("body", [{"name": "Taken over"}, {"name": ""}], ids=["valid", "invalid"])
async def test_ac19_admin_of_a_cannot_rename_b_gets_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, body: dict[str, Any]
) -> None:
    w = two_workspaces
    response = await db_client.patch(
        f"/v1/workspaces/{w.b.id}", json=body, headers=as_user(w.a_admin)
    )

    # Not 403 and not 422: nothing about workspace B may leak, not even that it exists.
    assert response.status_code == 404
    own = await db_client.get(f"/v1/workspaces/{w.b.id}", headers=as_user(w.b_admin))
    assert own.json()["name"] == "Workspace B"
