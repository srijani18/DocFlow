"""The per-request database session dependency. Kept apart from `app.core.db` so the
worker can use the engine and models without importing the web framework (ADR-0002)."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session (unit of work) per request.

    Commits when the endpoint returns normally, rolls back when it raises. Always use it
    through `DbSession`, never `Depends(get_session)` directly: see below.
    """
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        await session.commit()


# scope="function" makes FastAPI run the commit above *before* sending the response. With
# the default scope the exit code runs after the response is sent, so a failed commit
# would still reach the client as 200 OK.
DbSession = Annotated[AsyncSession, Depends(get_session, scope="function")]
