"""Baseline: pgvector in `extensions`, and lock the docflow schema away from Supabase roles.

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Supabase's browser-facing roles don't exist on plain Postgres (Docker, CI): skip them there.
REVOKE_SUPABASE_CLIENT_ROLES = """
DO $$
DECLARE client_role text;
BEGIN
  FOREACH client_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = client_role) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA docflow FROM %I', client_role);
    END IF;
  END LOOP;
END $$
"""


def upgrade() -> None:
    # Supabase convention: extensions in their own schema (it already exists there).
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
    # Defense in depth next to "Data API off" (ADR-0007): browser keys can never reach us.
    op.execute(REVOKE_SUPABASE_CLIENT_ROLES)


def downgrade() -> None:
    # The `extensions` and `docflow` schemas stay: Supabase owns the first, and the second
    # holds alembic_version.
    op.execute("DROP EXTENSION IF EXISTS vector")
