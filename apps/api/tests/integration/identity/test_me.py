import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User
from tests.support.identity import TwoWorkspaces, add_member
from tests.support.jwt import bearer, make_es256_key, supabase_claims


async def test_ac9_me_returns_user_and_memberships(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get(
        "/v1/me",
        headers=bearer(sub="new-user", email="ada@example.com", user_metadata={"name": "Ada"}),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["display_name"] == "Ada"
    assert [(m["workspace"]["name"], m["role"]) for m in body["memberships"]] == [
        ("Ada's workspace", "admin")
    ]


async def test_ac9_me_is_stable_across_requests(db_client: httpx.AsyncClient) -> None:
    first = (await db_client.get("/v1/me", headers=bearer(sub="same-user"))).json()
    second = (await db_client.get("/v1/me", headers=bearer(sub="same-user"))).json()

    assert first == second


async def test_ac9_me_lists_every_workspace_with_its_role(
    db_client: httpx.AsyncClient, db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    await add_member(db_session, w.b, w.a_admin, "reviewer")
    await db_session.commit()

    response = await db_client.get(
        "/v1/me", headers=bearer(sub=w.a_admin.auth_subject, email=w.a_admin.email)
    )

    memberships = {(m["workspace"]["id"], m["role"]) for m in response.json()["memberships"]}
    assert memberships == {(str(w.a.id), "admin"), (str(w.b.id), "reviewer")}


async def test_ac11_rejected_token_creates_nothing(
    db_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    forged = make_es256_key("test-key").sign(supabase_claims(sub="intruder"))

    response = await db_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


async def test_ac11_me_requires_a_token(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/v1/me")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
