"""Workspaces' own AI keys, encrypted; documents.failure_code (F15 plan §2).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_ai_keys",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("last4", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
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
            "provider IN ('gemini', 'groq', 'openrouter')",
            name=op.f("ck_workspace_ai_keys_provider"),
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'rejected', 'unchecked')", name=op.f("ck_workspace_ai_keys_status")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["docflow.users.id"],
            name=op.f("fk_workspace_ai_keys_updated_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_workspace_ai_keys_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "provider", name=op.f("pk_workspace_ai_keys")),
        schema="docflow",
    )
    op.add_column(
        "documents", sa.Column("failure_code", sa.Text(), nullable=True), schema="docflow"
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_column("documents", "failure_code", schema="docflow")
    op.drop_table("workspace_ai_keys", schema="docflow")
