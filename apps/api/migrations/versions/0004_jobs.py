"""Jobs: queue, document events, status columns (F3 plan §3).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
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
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('process_document')", name=op.f("ck_jobs_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'dead')", name=op.f("ck_jobs_status")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_jobs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_jobs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_jobs_idempotency_key")),
        schema="docflow",
    )
    op.create_index(
        "ix_jobs_claimable",
        "jobs",
        ["run_after"],
        unique=False,
        schema="docflow",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        op.f("ix_jobs_workspace_id"), "jobs", ["workspace_id"], unique=False, schema="docflow"
    )
    op.create_table(
        "document_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_document_events_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["docflow.jobs.id"],
            name=op.f("fk_document_events_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_document_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_events")),
        schema="docflow",
    )
    op.create_index(
        "ix_document_events_document",
        "document_events",
        ["document_id", "id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        op.f("ix_document_events_workspace_id"),
        "document_events",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column(
        "documents",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="docflow",
    )
    op.add_column(
        "documents",
        sa.Column(
            "processing_generation", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        schema="docflow",
    )
    # Autogenerate doesn't detect CHECK constraints; this one mirrors DocumentStatus.
    op.create_check_constraint(
        op.f("ck_documents_status"),
        "documents",
        "status IN ('UPLOADED', 'CLASSIFYING', 'EXTRACTING', 'NEEDS_REVIEW', 'FAILED')",
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_constraint(op.f("ck_documents_status"), "documents", type_="check", schema="docflow")
    op.drop_column("documents", "processing_generation", schema="docflow")
    op.drop_column("documents", "status_changed_at", schema="docflow")
    op.drop_index(
        op.f("ix_document_events_workspace_id"), table_name="document_events", schema="docflow"
    )
    op.drop_index("ix_document_events_document", table_name="document_events", schema="docflow")
    op.drop_table("document_events", schema="docflow")
    op.drop_index(op.f("ix_jobs_workspace_id"), table_name="jobs", schema="docflow")
    op.drop_index(
        "ix_jobs_claimable",
        table_name="jobs",
        schema="docflow",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_table("jobs", schema="docflow")
