"""Liveness and readiness endpoints (overview §10).

`/healthz` deliberately checks nothing: Render health checks and the cron keep-alive hit
it every few minutes, and touching the database would stop Neon from ever suspending.
"""

import asyncio

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import DatabaseUnavailableError
from app.core.logging import get_logger

READINESS_TIMEOUT_SECONDS = 5

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", responses={503: {"description": "A dependency is unavailable"}})
async def readyz(request: Request) -> dict[str, str]:
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("readiness_database_check_failed", error_type=type(exc).__name__)
        raise DatabaseUnavailableError() from exc
    return {"status": "ok", "database": "ok"}
