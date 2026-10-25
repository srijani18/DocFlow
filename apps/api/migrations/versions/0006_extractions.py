"""Versioned extractions and document summary columns (F5 plan §3).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "confidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("processing_generation", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('model', 'agent_fix', 'human')", name=op.f("ck_extractions_source")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["docflow.users.id"],
            name=op.f("fk_extractions_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_extractions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["docflow.llm_calls.id"],
            name=op.f("fk_extractions_llm_call_id_llm_calls"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_extractions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extractions")),
        schema="docflow",
    )
    op.create_index(
        op.f("ix_extractions_workspace_id"),
        "extractions",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        "uq_extractions_document_version",
        "extractions",
        ["document_id", "version"],
        unique=True,
        schema="docflow",
    )
    op.create_index(
        "uq_extractions_model_run",
        "extractions",
        ["document_id", "processing_generation"],
        unique=True,
        schema="docflow",
        postgresql_where=sa.text("source = 'model'"),
    )
    op.add_column(
        "documents", sa.Column("current_extraction_id", sa.Uuid(), nullable=True), schema="docflow"
    )
    op.add_column("documents", sa.Column("vendor_name", sa.Text(), nullable=True), schema="docflow")
    op.add_column(
        "documents", sa.Column("document_date", sa.Date(), nullable=True), schema="docflow"
    )
    op.add_column(
        "documents",
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        schema="docflow",
    )
    op.add_column(
        "documents", sa.Column("currency", sa.String(length=3), nullable=True), schema="docflow"
    )
    op.create_index(
        "ix_documents_workspace_date",
        "documents",
        ["workspace_id", "document_date"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        "ix_documents_workspace_vendor",
        "documents",
        ["workspace_id", "vendor_name"],
        unique=False,
        schema="docflow",
    )
    op.create_foreign_key(
        "fk_documents_current_extraction_id",
        "documents",
        "extractions",
        ["current_extraction_id"],
        ["id"],
        source_schema="docflow",
        referent_schema="docflow",
        use_alter=True,
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_constraint(
        "fk_documents_current_extraction_id", "documents", schema="docflow", type_="foreignkey"
    )
    op.drop_index("ix_documents_workspace_vendor", table_name="documents", schema="docflow")
    op.drop_index("ix_documents_workspace_date", table_name="documents", schema="docflow")
    op.drop_column("documents", "currency", schema="docflow")
    op.drop_column("documents", "total_amount", schema="docflow")
    op.drop_column("documents", "document_date", schema="docflow")
    op.drop_column("documents", "vendor_name", schema="docflow")
    op.drop_column("documents", "current_extraction_id", schema="docflow")
    op.drop_index(
        "uq_extractions_model_run",
        table_name="extractions",
        schema="docflow",
        postgresql_where=sa.text("source = 'model'"),
    )
    op.drop_index("uq_extractions_document_version", table_name="extractions", schema="docflow")
    op.drop_index(op.f("ix_extractions_workspace_id"), table_name="extractions", schema="docflow")
    op.drop_table("extractions", schema="docflow")
