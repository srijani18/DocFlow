import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from tests.conftest import asgi_client

PROBLEM_JSON = "application/problem+json"


class Payload(BaseModel):
    name: str = Field(min_length=1, max_length=5)
    count: int


def _add_test_routes(app: FastAPI) -> None:
    @app.post("/_test/validate")
    async def validate(payload: Payload) -> dict[str, str]:
        return {"name": payload.name}

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/_test/missing")
    async def missing() -> None:
        raise NotFoundError()


async def _client(app: FastAPI) -> httpx.AsyncClient:
    _add_test_routes(app)
    return await asgi_client(app)


async def test_validation_error_is_problem_json_with_field_errors(app: FastAPI) -> None:
    async with await _client(app) as client:
        response = await client.post("/_test/validate", json={"name": "toolong"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"].endswith("/validation")
    assert body["status"] == 422
    assert {error["field"] for error in body["errors"]} == {"name", "count"}
    assert body["request_id"] == response.headers["x-request-id"]


async def test_app_error_is_problem_json(app: FastAPI) -> None:
    async with await _client(app) as client:
        response = await client.get("/_test/missing")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"].endswith("/not-found")


async def test_unknown_route_is_problem_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"].endswith("/not-found")


async def test_unhandled_error_is_problem_500_with_request_id_and_no_stack(app: FastAPI) -> None:
    async with await _client(app) as client:
        response = await client.get("/_test/boom", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["x-request-id"] == "req-123"
    body = response.json()
    assert body["type"].endswith("/internal")
    assert body["request_id"] == "req-123"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
