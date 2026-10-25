"""Integration fixtures: a real, migrated Postgres (constitution §2.4).

- `db_session`: per-test transaction that is rolled back, so tests never see each other's
  data. Code under test may call `commit()`; it only releases a savepoint.
- `committing_engine`: for tests that need real commits across connections (e.g. races).
  Every table is truncated afterwards.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.auth.dependencies import get_token_verifier
from app.auth.verifier import TokenVerifier
from app.core.config import Settings
from app.core.db import Base, create_engine
from app.core.db_session import get_session
from app.events.dependencies import get_events, get_job_waker
from app.main import create_app
from app.models import import_all_models
from app.storage.dependencies import get_clock, get_storage
from app.storage.fake import FakeStorage
from tests.conftest import asgi_client, make_settings
from tests.support.clock import FrozenClock
from tests.support.identity import TwoWorkspaces, make_two_workspaces
from tests.support.jwt import TEST_ISSUER, TEST_SIGNING_KEY, StaticKeys
from tests.support.pipeline import Recorder

API_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:54320/docflow_test"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.path):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Bring the test database to the latest migration once per run."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(  # fixed argv, our own tool
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
    )
    import_all_models()


@pytest.fixture
def db_settings() -> Settings:
    return make_settings(database_url=TEST_DATABASE_URL)


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(make_settings(database_url=TEST_DATABASE_URL))
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_connection(db_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = AsyncSession(
        bind=db_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    yield session
    await session.close()


@pytest.fixture
async def committing_engine(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    yield db_engine
    tables = ", ".join(table.fullname for table in Base.metadata.sorted_tables)
    if tables:
        async with db_engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def fake_storage(clock: FrozenClock) -> FakeStorage:
    return FakeStorage(clock=clock)


@pytest.fixture
def published() -> Recorder:
    """Status events the API published (after commit)."""
    return Recorder()


@pytest.fixture
def wakeups() -> list[str]:
    """One entry per time the API woke the worker."""
    return []


@pytest.fixture
async def db_client(
    db_settings: Settings,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    clock: FrozenClock,
    published: Recorder,
    wakeups: list[str],
) -> AsyncIterator[httpx.AsyncClient]:
    """API client whose requests run inside the test's rolled-back transaction, and which
    trusts tokens signed with TEST_SIGNING_KEY (see `tests.support.jwt.bearer`). Storage is
    `fake_storage` and time is `clock`."""
    app: FastAPI = create_app(db_settings)

    async def session_in_test_transaction() -> AsyncIterator[AsyncSession]:
        try:
            yield db_session
        except Exception:
            await db_session.rollback()
            raise
        await db_session.commit()

    app.dependency_overrides[get_session] = session_in_test_transaction
    app.dependency_overrides[get_token_verifier] = lambda: TokenVerifier(
        StaticKeys(TEST_SIGNING_KEY), issuer=TEST_ISSUER
    )
    app.dependency_overrides[get_storage] = lambda: fake_storage
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_events] = lambda: published
    app.dependency_overrides[get_job_waker] = lambda: lambda: wakeups.append("wake")
    async with app.router.lifespan_context(app), await asgi_client(app) as http:
        yield http


@pytest.fixture
async def two_workspaces(db_session: AsyncSession) -> TwoWorkspaces:
    workspaces = await make_two_workspaces(db_session)
    # Like real pre-existing data: committed (here, a released savepoint), so a request
    # that fails and rolls back cannot take the fixture rows with it.
    await db_session.commit()
    return workspaces
