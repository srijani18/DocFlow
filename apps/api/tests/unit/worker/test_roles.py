import asyncio

import pytest

from app import __main__ as entrypoint
from app.core.config import ConfigError, Role, load_settings
from app.main import create_app
from tests.conftest import make_settings


async def test_role_api_has_routes_and_no_worker() -> None:
    app = create_app(make_settings(role="api"))

    async with app.router.lifespan_context(app):
        assert app.state.worker_task is None

    assert {"/healthz", "/readyz"} <= set(app.openapi()["paths"])


async def test_role_all_starts_and_stops_worker_cleanly() -> None:
    app = create_app(make_settings(role="all"))

    async with app.router.lifespan_context(app):
        task = app.state.worker_task
        await asyncio.sleep(0)  # let the worker start
        assert isinstance(task, asyncio.Task)
        assert not task.done()

    assert task.done()
    assert task.cancelled()


def test_role_worker_runs_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(entrypoint, "serve_http", lambda _settings: calls.append("http"))
    monkeypatch.setattr(entrypoint, "run_worker_process", lambda _settings: calls.append("worker"))

    entrypoint.main(make_settings(role="worker"))
    entrypoint.main(make_settings(role="api"))
    entrypoint.main(make_settings(role="all"))

    assert calls == ["worker", "http", "http"]


def test_invalid_role_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("ROLE", "scheduler")

    with pytest.raises(ConfigError, match="ROLE"):
        load_settings(env_file=None)


@pytest.mark.parametrize(
    ("role", "http", "worker"),
    [(Role.API, True, False), (Role.WORKER, False, True), (Role.ALL, True, True)],
)
def test_role_capabilities(role: Role, http: bool, worker: bool) -> None:
    assert role.serves_http is http
    assert role.runs_worker is worker
