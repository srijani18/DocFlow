from typing import Annotated

import httpx
import pytest
import respx
from fastapi import Depends, FastAPI

from app.auth.dependencies import get_token_verifier, get_verified_claims
from app.auth.verifier import TokenVerifier, VerifiedClaims
from app.main import create_app
from tests.conftest import asgi_client, make_settings
from tests.support.jwt import (
    TEST_ISSUER,
    TEST_JWKS_URL,
    StaticKeys,
    make_es256_key,
    supabase_claims,
)

KEY = make_es256_key("k1")
PROBLEM_JSON = "application/problem+json"


def _app_with_protected_route(*, static_keys: bool = True) -> FastAPI:
    app = create_app(make_settings())
    if static_keys:
        app.dependency_overrides[get_token_verifier] = lambda: TokenVerifier(
            StaticKeys(KEY), issuer=TEST_ISSUER
        )

    @app.get("/_test/protected")
    async def protected(
        claims: Annotated[VerifiedClaims, Depends(get_verified_claims)],
    ) -> dict[str, str]:
        return {"sub": claims.subject}

    return app


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Bearer " + make_es256_key("k1").sign(supabase_claims())},  # forged
    ],
    ids=["missing", "empty", "no-token", "basic", "malformed", "bad-signature"],
)
async def test_ac11_missing_or_invalid_token_returns_problem_401(headers: dict[str, str]) -> None:
    async with await asgi_client(_app_with_protected_route()) as client:
        response = await client.get("/_test/protected", headers=headers)

    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    body = response.json()
    assert body["type"].endswith("/unauthenticated")
    assert "detail" not in body  # the precise reason goes to the logs only


async def test_valid_token_reaches_the_endpoint() -> None:
    claims = supabase_claims()
    async with await asgi_client(_app_with_protected_route()) as client:
        response = await client.get(
            "/_test/protected", headers={"Authorization": f"Bearer {KEY.sign(claims)}"}
        )

    assert response.status_code == 200
    assert response.json() == {"sub": claims["sub"]}


@respx.mock
async def test_ac13_auth_unavailable_returns_503_retry_after() -> None:
    respx.get(TEST_JWKS_URL).mock(side_effect=httpx.ConnectError("provider down"))
    app = _app_with_protected_route(static_keys=False)  # the real JWKS cache

    async with await asgi_client(app) as client:
        response = await client.get(
            "/_test/protected", headers={"Authorization": f"Bearer {KEY.sign(supabase_claims())}"}
        )

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["retry-after"] == "5"
    assert response.json()["type"].endswith("/auth-unavailable")
