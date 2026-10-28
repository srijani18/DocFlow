"""F14 AC6, AC7: Idempotency-Key on write endpoints."""

from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.idempotency.models import IdempotencyKey
from app.mcp.models import ApiToken
from tests.support.documents import as_user
from tests.support.identity import TwoWorkspaces, UserRef


async def create_token(
    client: httpx.AsyncClient,
    w: TwoWorkspaces,
    user: UserRef,
    key: str | None,
    **body: Any,
) -> httpx.Response:
    headers = as_user(user) | ({"Idempotency-Key": key} if key else {})
    return await client.post(
        f"/v1/workspaces/{w.a.id}/api-tokens",
        json={"name": "laptop"} | body,
        headers=headers,
    )


async def tokens_in(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(ApiToken)) or 0


async def test_ac6_a_repeat_returns_the_first_response_and_does_nothing_again(
    db_client: httpx.AsyncClient, db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces

    first = await create_token(db_client, w, w.a_admin, "create-1")
    repeat = await create_token(db_client, w, w.a_admin, "create-1")

    assert first.status_code == repeat.status_code == 201
    assert repeat.json() == first.json()  # the same token: nothing was created again
    assert repeat.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in first.headers
    assert await tokens_in(db_session) == 1


async def test_ac6_without_a_key_or_with_another_key_each_request_acts(
    db_client: httpx.AsyncClient, db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces

    await create_token(db_client, w, w.a_admin, None)
    await create_token(db_client, w, w.a_admin, None)
    await create_token(db_client, w, w.a_admin, "one")
    await create_token(db_client, w, w.a_admin, "two")
    other_user = await create_token(db_client, w, w.a_reviewer, "one")  # keys are per user

    assert other_user.status_code == 201
    assert await tokens_in(db_session) == 5


async def test_ac7_the_same_key_with_a_different_request_is_refused(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    await create_token(db_client, w, w.a_admin, "k")

    changed = await create_token(db_client, w, w.a_admin, "k", name="desktop")

    assert changed.status_code == 422
    assert changed.json()["type"].endswith("/idempotency-key-reused")


async def test_ac7_a_repeat_while_the_first_is_running_gets_409(
    db_client: httpx.AsyncClient, db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    await create_token(db_client, w, w.a_admin, "slow")
    # As if the first request were still running.
    await db_session.execute(update(IdempotencyKey).values(status="running", updated_at=func.now()))

    repeat = await create_token(db_client, w, w.a_admin, "slow")

    assert repeat.status_code == 409
    assert repeat.json()["type"].endswith("/idempotency-key-in-progress")
    assert repeat.headers["retry-after"] == "1"


async def test_ac6_a_failed_request_releases_its_key(
    db_client: httpx.AsyncClient, db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    base = f"/v1/workspaces/{w.a.id}/api-tokens"
    headers = as_user(w.a_admin) | {"Idempotency-Key": "revoke-1"}

    missing = await db_client.delete(
        f"{base}/00000000-0000-0000-0000-000000000000", headers=headers
    )
    keys = await db_session.scalar(select(func.count()).select_from(IdempotencyKey))

    assert missing.status_code == 404
    assert keys == 0


async def test_ac6_bad_keys_are_rejected(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces

    too_long = await create_token(db_client, w, w.a_admin, "x" * 256)

    assert too_long.status_code == 422
    assert too_long.json()["type"].endswith("/invalid-idempotency-key")
