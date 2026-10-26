import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from tests.conftest import asgi_client, make_settings

ORIGIN = "http://localhost:3000"


@pytest.fixture
def cors_app() -> FastAPI:
    return create_app(make_settings(cors_allowed_origins=[ORIGIN]))


def methods_used_by_the_api(app: FastAPI) -> set[str]:
    return {
        method.upper()
        for operations in app.openapi()["paths"].values()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }


async def test_every_api_method_passes_the_browser_preflight(cors_app: FastAPI) -> None:
    """A method the API uses but CORS doesn't allow fails only in real browsers (found by
    the F15 live check: PUT /ai-keys/{provider} got a 400 preflight)."""
    methods = methods_used_by_the_api(cors_app)
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= methods

    async with await asgi_client(cors_app) as client:
        for method in sorted(methods):
            response = await client.options(
                "/v1/me",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert response.status_code == 200, method
            assert method in response.headers["access-control-allow-methods"]


async def test_unknown_origin_is_not_allowed(cors_app: FastAPI) -> None:
    async with await asgi_client(cors_app) as client:
        response: httpx.Response = await client.options(
            "/v1/me",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )

    assert "access-control-allow-origin" not in response.headers
