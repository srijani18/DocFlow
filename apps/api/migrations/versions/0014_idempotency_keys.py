"""Stored outcomes of write requests sent with an Idempotency-Key (F14 plan §3).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'running'"), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_type", sa.Text(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done')", name=op.f("ck_idempotency_keys_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["docflow.users.id"],
            name=op.f("fk_idempotency_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_idempotency_keys_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        schema="docflow",
    )
    op.create_index(
        op.f("ix_idempotency_keys_workspace_id"),
        "idempotency_keys",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        "uq_idempotency_keys_key",
        "idempotency_keys",
        ["workspace_id", "user_id", "key"],
        unique=True,
        schema="docflow",
    )

    # A tenant table: row-level security like every other (F14 AC1, migration 0013).
    op.execute("ALTER TABLE docflow.idempotency_keys ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant ON docflow.idempotency_keys TO docflow_app "
        "USING (workspace_id = docflow.current_workspace()) "
        "WITH CHECK (workspace_id = docflow.current_workspace())"
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.execute("DROP POLICY tenant ON docflow.idempotency_keys")
    op.drop_index("uq_idempotency_keys_key", table_name="idempotency_keys", schema="docflow")
    op.drop_index(
        op.f("ix_idempotency_keys_workspace_id"), table_name="idempotency_keys", schema="docflow"
    )
    op.drop_table("idempotency_keys", schema="docflow")
