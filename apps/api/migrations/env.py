"""Alembic environment.

The URL comes from app settings (DATABASE_URL, the Supabase session pooler), never from
alembic.ini. Everything, including `alembic_version`, lives in the `docflow` schema
(ADR-0007). Connections use MIGRATIONS_SEARCH_PATH so `docflow` is compared by name.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import DatabaseSettings, load_settings
from app.core.db import DB_SCHEMA, MIGRATIONS_SEARCH_PATH, Base, create_engine
from app.models import import_all_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

import_all_models()
target_metadata = Base.metadata


def _include_name(name: str | None, type_: str, _parent: object) -> bool:
    # Autogenerate and `alembic check` look only at our schema, never at Supabase's.
    return name == DB_SCHEMA if type_ == "schema" else True


def run_migrations_offline() -> None:
    context.configure(
        url=load_settings(settings_class=DatabaseSettings).database_url,
        target_metadata=target_metadata,
        version_table_schema=DB_SCHEMA,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=DB_SCHEMA,
        include_schemas=True,
        include_name=_include_name,
        transaction_per_migration=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(
        load_settings(settings_class=DatabaseSettings), search_path=MIGRATIONS_SEARCH_PATH
    )
    # The version table lives in our schema, so the schema must exist before Alembic
    # reads or creates it. Idempotent; never dropped by a downgrade.
    async with engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
