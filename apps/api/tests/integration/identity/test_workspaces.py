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
