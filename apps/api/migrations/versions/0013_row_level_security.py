"""Row-level security on every tenant table (F14 plan §1, ADR-0009).

Tenant transactions run as `docflow_app`, which can't bypass RLS, with the transaction-local
setting `docflow.workspace_id`. Each tenant table allows only rows of that workspace. The table
owner (the migration user) bypasses RLS, which is what system operations use.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "docflow_app"
SETTING = "docflow.workspace_id"

# Every table with a workspace_id column gets the same policy (the tenant meta-test checks
# that none is missed); the tenant root matches on its own id.
TENANT_TABLES = """
    SELECT c.table_name FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.table_schema = 'docflow' AND c.column_name = 'workspace_id'
      AND t.table_type = 'BASE TABLE'
"""


def upgrade() -> None:
    # Roles are cluster-wide: the dev and test databases share one, so create it only once.
    op.execute(f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} NOLOGIN NOBYPASSRLS;
          END IF;
          -- Postgres 16+ no longer lets a role creator switch to the new role by default
          -- (Supabase's postgres has CREATEROLE but isn't a superuser).
          IF current_setting('server_version_num')::int >= 160000 THEN
            EXECUTE format('GRANT {APP_ROLE} TO %I WITH SET TRUE, INHERIT FALSE', current_user);
          ELSE
            EXECUTE format('GRANT {APP_ROLE} TO %I', current_user);
          END IF;
        END $$
    """)
    op.execute(f"GRANT USAGE ON SCHEMA docflow TO {APP_ROLE}")
    # pgvector's types and operators live in `extensions` (Supabase convention).
    op.execute(f"GRANT USAGE ON SCHEMA extensions TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA docflow TO {APP_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA docflow TO {APP_ROLE}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA docflow "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA docflow GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )
    op.execute(f"""
        CREATE FUNCTION docflow.current_workspace() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT nullif(current_setting('{SETTING}', true), '')::uuid $$
    """)
    op.execute(f"""
        DO $$ DECLARE t text; BEGIN
          FOR t IN {TENANT_TABLES} LOOP
            EXECUTE format('ALTER TABLE docflow.%I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format(
              'CREATE POLICY tenant ON docflow.%I TO {APP_ROLE} '
              'USING (workspace_id = docflow.current_workspace()) '
              'WITH CHECK (workspace_id = docflow.current_workspace())', t);
          END LOOP;
        END $$
    """)
    op.execute("ALTER TABLE docflow.workspaces ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant ON docflow.workspaces TO {APP_ROLE}
        USING (id = docflow.current_workspace()) WITH CHECK (id = docflow.current_workspace())
    """)


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible. The role itself stays: other
    # databases on the same server may still use it.
    op.execute("DROP POLICY tenant ON docflow.workspaces")
    op.execute("ALTER TABLE docflow.workspaces DISABLE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ DECLARE t text; BEGIN
          FOR t IN {TENANT_TABLES} LOOP
            EXECUTE format('DROP POLICY tenant ON docflow.%I', t);
            EXECUTE format('ALTER TABLE docflow.%I DISABLE ROW LEVEL SECURITY', t);
          END LOOP;
        END $$
    """)
    op.execute("DROP FUNCTION docflow.current_workspace()")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA docflow "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA docflow "  # noqa: S608  # a constant role name
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA docflow FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA docflow FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA docflow FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA extensions FROM {APP_ROLE}")
