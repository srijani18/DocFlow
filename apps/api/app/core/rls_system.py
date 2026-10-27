"""System database access: work that legitimately spans workspaces runs as the table owner,
which bypasses row-level security (F14 AC3, ADR-0009).

Only the modules an import-linter contract allows may use this: identity (sign-in,
provisioning, one's own memberships), the job queue, and operator tools. Everything else acts
for one workspace.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import create_sessionmaker
from app.core.rls import DEFAULT, EXPLICIT, SYSTEM, apply_now


def system_session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncSession:
    return sessionmaker(info={EXPLICIT: SYSTEM})


async def become_system(session: AsyncSession) -> None:
    """Switch a session to system access, including its current transaction."""
    session.info[EXPLICIT] = SYSTEM
    await apply_now(session)


def system_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions that are system unless the task acts for a workspace: for operator tools
    and tests' seeding."""
    return create_sessionmaker(engine, info={DEFAULT: SYSTEM})
