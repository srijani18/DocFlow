"""Database engine and sessions (SQLAlchemy 2 async, psycopg 3).

The app connects through Neon's *pooled* connection string; migrations use the direct one
(constitution §7.3). Creating the engine does not connect, so startup never waits on a
sleeping Neon compute.
"""

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings

# Stable constraint names make migrations reproducible and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


CONNECT_TIMEOUT_SECONDS = 10


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        # Small pool: one instance, and Neon's pooler multiplexes behind it.
        pool_size=5,
        max_overflow=0,
        # Neon may have suspended the compute or closed idle connections.
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
