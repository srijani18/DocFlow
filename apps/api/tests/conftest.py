from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

# Points at a closed port: unit tests must never need a database.
UNREACHABLE_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:1/unreachable"


def make_settings(**overrides: Any) -> Settings:
    """Build settings without reading the environment or any .env file."""
    values: dict[str, Any] = {
        "environment": "test",
        "role": "api",
        "database_url": UNREACHABLE_DATABASE_URL,
    }
    return Settings.model_validate(values | overrides)


async def asgi_client(app: FastAPI) -> httpx.AsyncClient:
    # raise_app_exceptions=False: assert on the 500 response instead of the raw exception.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with await asgi_client(app) as http:
        yield http
