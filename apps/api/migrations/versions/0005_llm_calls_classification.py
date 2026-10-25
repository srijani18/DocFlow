"""LLM call log and document classification (F4 plan §3).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('ok', 'error', 'invalid_output')", name=op.f("ck_llm_calls_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_llm_calls_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["docflow.jobs.id"],
            name=op.f("fk_llm_calls_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_llm_calls_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
        schema="docflow",
    )
    op.create_index(
        op.f("ix_llm_calls_document_id"),
        "llm_calls",
        ["document_id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        op.f("ix_llm_calls_workspace_id"),
        "llm_calls",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column("documents", sa.Column("doc_type", sa.Text(), nullable=True), schema="docflow")
    op.add_column(
        "documents", sa.Column("doc_type_confidence", sa.REAL(), nullable=True), schema="docflow"
    )
    # Autogenerate doesn't detect CHECK constraints; these mirror DocType and the 0..1 range.
    op.create_check_constraint(
        op.f("ck_documents_doc_type"),
        "documents",
        "doc_type IN ('invoice', 'receipt', 'purchase_order', 'other')",
        schema="docflow",
    )
    op.create_check_constraint(
        op.f("ck_documents_doc_type_confidence"),
        "documents",
        "doc_type_confidence BETWEEN 0 AND 1",
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_constraint(
        op.f("ck_documents_doc_type_confidence"), "documents", type_="check", schema="docflow"
    )
    op.drop_constraint(op.f("ck_documents_doc_type"), "documents", type_="check", schema="docflow")
    op.drop_column("documents", "doc_type_confidence", schema="docflow")
    op.drop_column("documents", "doc_type", schema="docflow")
    op.drop_index(op.f("ix_llm_calls_workspace_id"), table_name="llm_calls", schema="docflow")
    op.drop_index(op.f("ix_llm_calls_document_id"), table_name="llm_calls", schema="docflow")
    op.drop_table("llm_calls", schema="docflow")
