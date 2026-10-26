"""LLM gateway: route position, fallback and input mode on llm_calls; response cache (F10).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_cache",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("source_call_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_call_id"],
            ["docflow.llm_calls.id"],
            name=op.f("fk_llm_cache_source_call_id_llm_calls"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_llm_cache_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_llm_cache")),
        schema="docflow",
    )
    op.create_index(
        op.f("ix_llm_cache_workspace_id"),
        "llm_cache",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column(
        "llm_calls",
        sa.Column("route_position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="docflow",
    )
    op.add_column(
        "llm_calls",
        sa.Column("fallback", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="docflow",
    )
    op.add_column("llm_calls", sa.Column("input_mode", sa.Text(), nullable=True), schema="docflow")
    # Autogenerate doesn't detect CHECK changes: widen the allowed outcomes.
    op.drop_constraint(op.f("ck_llm_calls_outcome"), "llm_calls", type_="check", schema="docflow")
    op.create_check_constraint(
        op.f("ck_llm_calls_outcome"),
        "llm_calls",
        "outcome IN ('ok', 'error', 'invalid_output', 'cache_hit', 'skipped')",
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible. Rows with the new outcomes
    # can't satisfy the old constraint, so they are removed first.
    op.execute("DELETE FROM docflow.llm_calls WHERE outcome IN ('cache_hit', 'skipped')")
    op.drop_constraint(op.f("ck_llm_calls_outcome"), "llm_calls", type_="check", schema="docflow")
    op.create_check_constraint(
        op.f("ck_llm_calls_outcome"),
        "llm_calls",
        "outcome IN ('ok', 'error', 'invalid_output')",
        schema="docflow",
    )
    op.drop_column("llm_calls", "input_mode", schema="docflow")
    op.drop_column("llm_calls", "fallback", schema="docflow")
    op.drop_column("llm_calls", "route_position", schema="docflow")
    op.drop_index(op.f("ix_llm_cache_workspace_id"), table_name="llm_cache", schema="docflow")
    op.drop_table("llm_cache", schema="docflow")
