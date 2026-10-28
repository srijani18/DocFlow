"""F14 AC9, AC10: rate limits per user and per access token."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.ratelimit import RateLimiter
from tests.support.documents import PDF, as_user, start
from tests.support.identity import TwoWorkspaces


@pytest.fixture(autouse=True)
def tiny_limits(db_app: FastAPI) -> None:
    db_app.state.rate_limiter = RateLimiter({"general": 4, "uploads": 1, "ai": 1, "mcp": 1})


async def test_ac9_ac10_over_the_general_limit_gets_429_with_retry_after(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    statuses = [
        (await db_client.get("/v1/me", headers=as_user(w.a_admin))).status_code for _ in range(4)
    ]

    refused = await db_client.get("/v1/me", headers=as_user(w.a_admin))
    someone_else = await db_client.get("/v1/me", headers=as_user(w.a_reviewer))
    health = [(await db_client.get("/healthz")).status_code for _ in range(10)]

    assert statuses == [200] * 4
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "15"
    assert refused.headers["content-type"] == "application/problem+json"
    assert refused.json()["type"].endswith("/rate-limited")
    assert refused.json()["detail"] == "Too many requests. Try again in 15 s."
    assert someone_else.status_code == 200
    assert set(health) == {200}


async def test_ac9_uploads_and_ai_searches_have_their_own_limits(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    search = f"/v1/workspaces/{w.a.id}/search"

    first_upload = await start(db_client, w.a.id, w.a_admin)
    second_upload = await start(db_client, w.a.id, w.a_admin, PDF + b"other")
    first_search = await db_client.get(
        search, params={"q": "kaveri"}, headers=as_user(w.a_reviewer)
    )
    listing = await db_client.get(search, headers=as_user(w.a_reviewer))  # no text: no AI
    second_search = await db_client.get(
        search, params={"q": "tiffin"}, headers=as_user(w.a_reviewer)
    )

    assert (first_upload.status_code, second_upload.status_code) == (201, 429)
    assert (first_search.status_code, listing.status_code, second_search.status_code) == (
        200,
        200,
        429,
    )
