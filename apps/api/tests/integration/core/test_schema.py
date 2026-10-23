"""ADR-0007: DocFlow keeps everything in its own schema, never in Supabase's `public`."""

import importlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.db import DB_SCHEMA, Base, create_engine


async def test_migrations_live_in_the_docflow_schema(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        schemas = (
            (
                await connection.execute(
                    text(
                        "SELECT table_schema FROM information_schema.tables "
                        "WHERE table_name = 'alembic_version'"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert schemas == [DB_SCHEMA]


def test_orm_tables_default_to_the_docflow_schema() -> None:
    assert Base.metadata.schema == DB_SCHEMA


async def test_connections_search_docflow_then_extensions(db_settings: Settings) -> None:
    engine = create_engine(db_settings)
    try:
        async with engine.connect() as connection:
            # A rolled-back transaction must not undo the session-level setting.
            await connection.rollback()
            search_path = await connection.scalar(text("SHOW search_path"))
    finally:
        await engine.dispose()

    assert search_path == "docflow, extensions, public"


async def test_vector_extension_lives_in_the_extensions_schema(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        schema = await connection.scalar(
            text(
                "SELECT n.nspname FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
            )
        )

    assert schema == "extensions"


async def test_baseline_revokes_supabase_client_roles(db_session: AsyncSession) -> None:
    # Simulate Supabase: the roles exist and were granted access. All inside the test's
    # rolled-back transaction, so the roles never persist.
    baseline = importlib.import_module("migrations.versions.0001_baseline")
    for role in ("anon", "authenticated"):
        await db_session.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        await db_session.execute(text(f"GRANT USAGE ON SCHEMA docflow TO {role}"))

    await db_session.execute(text(baseline.REVOKE_SUPABASE_CLIENT_ROLES))

    for role in ("anon", "authenticated"):
        can_use = await db_session.scalar(
            text("SELECT has_schema_privilege(:role, 'docflow', 'USAGE')"), {"role": role}
        )
        assert can_use is False
