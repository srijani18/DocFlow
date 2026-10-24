"""Database engine and sessions (SQLAlchemy 2 async, psycopg 3).

Production is Supabase Postgres through the shared pooler in session mode (ADR-0007): one
connection string for the app and for Alembic. Every DocFlow table lives in the `docflow`
schema, never in Supabase's `public` schema. Creating the engine does not connect.
"""

from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import MetaData, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import Settings

# Stable constraint names make migrations reproducible and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


DB_SCHEMA = "docflow"
# `extensions` is where Supabase installs pgvector; `public` stays last for anything else.
SEARCH_PATH = f"{DB_SCHEMA}, extensions, public"
# Alembic must see `docflow` as a named, non-default schema, or autogenerate can't match
# reflected tables to the schema-qualified models. Unqualified DDL in a migration would land
# in `public`, which a test forbids.
MIGRATIONS_SEARCH_PATH = "public, extensions"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=DB_SCHEMA)


CONNECT_TIMEOUT_SECONDS = 10


def _search_path_setter(search_path: str) -> Callable[[DBAPIConnection, ConnectionPoolEntry], None]:
    def set_search_path(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
        # Autocommit, so the setting is not undone when the first transaction rolls back.
        # A plain SET (not a startup option) works through Supavisor's session mode.
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET SESSION search_path TO {search_path}")
        cursor.close()
        dbapi_connection.autocommit = previous

    return set_search_path


def create_engine(settings: Settings, *, search_path: str = SEARCH_PATH) -> AsyncEngine:
    engine = create_async_engine(
        settings.database_url,
        # Small pool: one instance. In session mode each client connection holds one
        # pooler connection, so this is also our share of Supabase's connection limit.
        pool_size=5,
        max_overflow=0,
        # The pooler or the network may have dropped idle connections.
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    # insert=True: run before SQLAlchemy's own first-connect setup, which records the
    # default schema; otherwise it would see the server default, not our search_path.
    event.listen(engine.sync_engine, "connect", _search_path_setter(search_path), insert=True)
    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


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
