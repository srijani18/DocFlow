import os
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests.conftest import asgi_client, make_settings

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://docflow:docflow@localhost:54320/docflow_test"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.path):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def db_settings() -> Settings:
    return make_settings(database_url=TEST_DATABASE_URL)


@pytest.fixture
async def db_client(db_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(db_settings)
    async with app.router.lifespan_context(app), await asgi_client(app) as http:
        yield http
