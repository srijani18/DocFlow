"""Constitution §4.6: every table is tenant-scoped unless it is explicitly global.

Inspects the real, migrated database (not the ORM models), so a hand-written migration
that forgets `workspace_id` or its index fails here too.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import DB_SCHEMA

# Tables that are global by design. Adding one needs a reason in the PR.
GLOBAL_TABLES = {
    "alembic_version",  # Alembic bookkeeping
    "users",  # a person can belong to several workspaces
    "workspaces",  # the tenant root itself
}

TENANT_COLUMN_CHECK = text(
    """
    SELECT
      t.table_name,
      c.is_nullable = 'NO' AS not_null,
      EXISTS (
        SELECT 1 FROM pg_constraint fk
        JOIN pg_class src ON src.oid = fk.conrelid
        JOIN pg_namespace ns ON ns.oid = src.relnamespace
        JOIN pg_class dst ON dst.oid = fk.confrelid
        JOIN pg_attribute a ON a.attrelid = fk.conrelid AND a.attnum = fk.conkey[1]
        WHERE fk.contype = 'f' AND ns.nspname = :schema AND src.relname = t.table_name
          AND dst.relname = 'workspaces' AND a.attname = 'workspace_id'
      ) AS has_fk,
      EXISTS (
        SELECT 1 FROM pg_index ix
        JOIN pg_class tbl ON tbl.oid = ix.indrelid
        JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
        JOIN pg_attribute a ON a.attrelid = tbl.oid AND a.attnum = ix.indkey[0]
        WHERE ns.nspname = :schema AND tbl.relname = t.table_name AND a.attname = 'workspace_id'
      ) AS has_leading_index
    FROM information_schema.tables t
    LEFT JOIN information_schema.columns c
      ON c.table_schema = t.table_schema AND c.table_name = t.table_name
     AND c.column_name = 'workspace_id'
    WHERE t.table_schema = :schema AND t.table_type = 'BASE TABLE'
    """
)


async def test_every_table_is_tenant_scoped_or_explicitly_global(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        rows = (await connection.execute(TENANT_COLUMN_CHECK, {"schema": DB_SCHEMA})).all()

    problems = [
        f"{row.table_name}: needs workspace_id NOT NULL, an FK to workspaces and a leading index"
        for row in rows
        if row.table_name not in GLOBAL_TABLES
        and not (row.not_null and row.has_fk and row.has_leading_index)
    ]
    assert not problems, "\n".join(problems)
    assert {row.table_name for row in rows} >= {"memberships"}, "the check must see tenant tables"
