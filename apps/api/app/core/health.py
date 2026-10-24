"""Liveness and readiness endpoints (overview §10).

`/healthz` is liveness and deliberately checks nothing: if it depended on the database,
a database blip would make Render restart a perfectly healthy process.
`/readyz` checks the database. The cron keep-alive calls it, which keeps both the Render
service and the Supabase project active (ADR-0007).
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
