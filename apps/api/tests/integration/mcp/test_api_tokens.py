"""F12 AC1-AC3: workspace access tokens."""

from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Membership
from app.mcp import tokens
from tests.support.clock import FrozenClock
from tests.support.documents import as_user
from tests.support.identity import TwoWorkspaces, UserRef


async def create(
    client: httpx.AsyncClient, w: TwoWorkspaces, user: UserRef, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/v1/workspaces/{w.a.id}/api-tokens",
        json={"name": "Claude Code"} | body,
        headers=as_user(user),
    )


async def listed(client: httpx.AsyncClient, w: TwoWorkspaces, user: UserRef) -> list[Any]:
    response = await client.get(f"/v1/workspaces/{w.a.id}/api-tokens", headers=as_user(user))
    assert response.status_code == 200, response.text
    body: list[Any] = response.json()
    return body


async def test_ac1_token_is_shown_once(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, clock: FrozenClock
) -> None:
    w = two_workspaces

    created = await create(db_client, w, w.a_reviewer, expires_in_days=30)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["token"].startswith("dfw_")
    assert len(body["token"]) > 40
    assert body["prefix"] == body["token"][:8]
    assert body["expires_at"].startswith(str((clock.now() + timedelta(days=30)).date()))
    [token] = await listed(db_client, w, w.a_reviewer)
    assert "token" not in token
    assert token["prefix"] == body["prefix"]
    assert (token["active"], token["created_by"]) == (True, "a-reviewer@example.com")


async def test_ac3_members_see_their_own_and_admins_see_all(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    mine = (await create(db_client, w, w.a_reviewer, name="mine")).json()
    admins = (await create(db_client, w, w.a_admin, name="admin's")).json()
    base = f"/v1/workspaces/{w.a.id}/api-tokens"

    reviewer_view = await listed(db_client, w, w.a_reviewer)
    revoke_admins = await db_client.delete(f"{base}/{admins['id']}", headers=as_user(w.a_reviewer))
    outsider = await db_client.get(base, headers=as_user(w.b_admin))
    revoke_mine = await db_client.delete(f"{base}/{mine['id']}", headers=as_user(w.a_admin))
    again = await db_client.delete(f"{base}/{mine['id']}", headers=as_user(w.a_admin))
    admin_view = await listed(db_client, w, w.a_admin)

    assert [token["name"] for token in reviewer_view] == ["mine"]
    assert revoke_admins.status_code == 404
    assert outsider.status_code == 404
    assert (revoke_mine.status_code, again.status_code) == (204, 204)
    assert {token["name"]: token["active"] for token in admin_view} == {
        "mine": False,
        "admin's": True,
    }


async def test_ac1_name_and_expiry_are_validated(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces

    no_name = await create(db_client, w, w.a_admin, name="")
    odd_expiry = await create(db_client, w, w.a_admin, expires_in_days=7)

    assert (no_name.status_code, odd_expiry.status_code) == (422, 422)


async def test_ac2_tokens_stop_working_when_expired_or_the_member_leaves(
    db_client: httpx.AsyncClient,
    db_session: AsyncSession,
    two_workspaces: TwoWorkspaces,
    clock: FrozenClock,
) -> None:
    w = two_workspaces
    reviewers = (await create(db_client, w, w.a_reviewer, expires_in_days=30)).json()["token"]
    admins = (await create(db_client, w, w.a_admin, expires_in_days=30)).json()["token"]

    valid = await tokens.verify_token(db_session, admins, now=clock.now())
    await db_session.execute(
        delete(Membership).where(
            Membership.workspace_id == w.a.id, Membership.user_id == w.a_reviewer.id
        )
    )
    left = await tokens.verify_token(db_session, reviewers, now=clock.now())
    expired = await tokens.verify_token(db_session, admins, now=clock.now() + timedelta(days=31))
    garbage = await tokens.verify_token(db_session, "not-a-token", now=clock.now())

    assert valid is not None
    assert (valid.scope.workspace_id, valid.scope.user_id, valid.scope.role) == (
        w.a.id,
        w.a_admin.id,
        "admin",
    )
    assert (left, expired, garbage) == (None, None, None)
    [admin_view] = [
        t for t in await listed(db_client, w, w.a_admin) if t["created_by"] != "a-admin@example.com"
    ]
    assert admin_view["active"] is False
