"""Application factory. `ROLE` decides what this process runs (ADR-0002)."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.core import health
from app.core.config import Settings, load_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from app.worker.loop import Worker


def _operation_id(route: APIRoute) -> str:
    # get_me -> getMe: stable, readable names in openapi.json and the generated TS client.
    first, *rest = route.name.split("_")
    return first + "".join(part.capitalize() for part in rest)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings)
    engine = create_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ROLE=all runs the worker as a task inside the API process (ADR-0002).
        worker_task = None
        if settings.role.runs_worker:
            worker_task = asyncio.create_task(app.state.worker.run(), name="worker")
        app.state.worker_task = worker_task
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task
            await engine.dispose()

    app = FastAPI(
        title="DocFlow API",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.worker = Worker() if settings.role.runs_worker else None

    install_error_handlers(app)
    # Starlette runs the last-added middleware first: CORS wraps everything, so even
    # last-resort 500s carry CORS headers and the browser can read them.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health.router)
    return app
