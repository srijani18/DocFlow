from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.core.db_session import DbSession
from app.main import create_app
from tests.conftest import asgi_client

SCRATCH_DDL = "CREATE TABLE IF NOT EXISTS _scratch (v int UNIQUE DEFERRABLE INITIALLY DEFERRED)"


@pytest.fixture
async def app_with_scratch_table(db_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(db_settings)

    @app.post("/_test/insert/{value}")
    async def insert(value: int, session: DbSession) -> dict[str, int]:
        await session.execute(text("INSERT INTO _scratch (v) VALUES (:v)"), {"v": value})
        if value < 0:
            raise RuntimeError("fail after write")
        return {"v": value}

    @app.post("/_test/insert-twice/{value}")
    async def insert_twice(value: int, session: DbSession) -> dict[str, int]:
        # The unique constraint is deferred, so the violation surfaces only at COMMIT.
        for _ in range(2):
            await session.execute(text("INSERT INTO _scratch (v) VALUES (:v)"), {"v": value})
        return {"v": value}

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.execute(text(SCRATCH_DDL))
            await conn.execute(text("TRUNCATE _scratch"))
        yield app
        async with app.state.engine.begin() as conn:
            await conn.execute(text("DROP TABLE _scratch"))


async def _values(app: FastAPI) -> list[int]:
    async with app.state.engine.connect() as conn:
        return list((await conn.execute(text("SELECT v FROM _scratch ORDER BY v"))).scalars())


async def test_session_dependency_commits_and_rolls_back(app_with_scratch_table: FastAPI) -> None:
    app = app_with_scratch_table
    async with await asgi_client(app) as client:
        ok = await client.post("/_test/insert/1")
        failed = await client.post("/_test/insert/-1")

    assert ok.status_code == 200
    assert failed.status_code == 500
    assert await _values(app) == [1]


async def test_failed_commit_is_an_error_response_not_200(app_with_scratch_table: FastAPI) -> None:
    app = app_with_scratch_table
    async with await asgi_client(app) as client:
        response = await client.post("/_test/insert-twice/7")

    assert response.status_code == 500
    assert await _values(app) == []
