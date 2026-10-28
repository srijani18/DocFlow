"""Validation: issues per extraction, approval columns, VALIDATING and APPROVED (F6 plan §3).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_issues",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("check_name", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("paths", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("fixed_by_agent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('error', 'warning', 'info')", name=op.f("ck_validation_issues_severity")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_validation_issues_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["docflow.extractions.id"],
            name=op.f("fk_validation_issues_extraction_id_extractions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_validation_issues_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_issues")),
        schema="docflow",
    )
    op.create_index(
        "ix_validation_issues_extraction",
        "validation_issues",
        ["extraction_id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        op.f("ix_validation_issues_workspace_id"),
        "validation_issues",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column(
        "documents",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        schema="docflow",
    )
    op.add_column(
        "documents", sa.Column("approved_by_user_id", sa.Uuid(), nullable=True), schema="docflow"
    )
    op.add_column(
        "documents",
        sa.Column(
            "approved_by_agent", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        schema="docflow",
    )
    op.create_foreign_key(
        op.f("fk_documents_approved_by_user_id_users"),
        "documents",
        "users",
        ["approved_by_user_id"],
        ["id"],
        source_schema="docflow",
        referent_schema="docflow",
    )
    # Autogenerate doesn't detect CHECK changes: allow the new statuses.
    op.drop_constraint(op.f("ck_documents_status"), "documents", type_="check", schema="docflow")
    op.create_check_constraint(
        op.f("ck_documents_status"),
        "documents",
        "status IN ('UPLOADED', 'CLASSIFYING', 'EXTRACTING', 'VALIDATING', 'NEEDS_REVIEW', "
        "'APPROVED', 'FAILED')",
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible. Documents in the new statuses
    # go back to the closest old one first.
    op.execute(
        "UPDATE docflow.documents SET status = CASE status WHEN 'VALIDATING' THEN 'EXTRACTING' "
        "ELSE 'NEEDS_REVIEW' END WHERE status IN ('VALIDATING', 'APPROVED')"
    )
    op.drop_constraint(op.f("ck_documents_status"), "documents", type_="check", schema="docflow")
    op.create_check_constraint(
        op.f("ck_documents_status"),
        "documents",
        "status IN ('UPLOADED', 'CLASSIFYING', 'EXTRACTING', 'NEEDS_REVIEW', 'FAILED')",
        schema="docflow",
    )
    op.drop_constraint(
        op.f("fk_documents_approved_by_user_id_users"),
        "documents",
        schema="docflow",
        type_="foreignkey",
    )
    op.drop_column("documents", "approved_by_agent", schema="docflow")
    op.drop_column("documents", "approved_by_user_id", schema="docflow")
    op.drop_column("documents", "approved_at", schema="docflow")
    op.drop_index(
        op.f("ix_validation_issues_workspace_id"), table_name="validation_issues", schema="docflow"
    )
    op.drop_index(
        "ix_validation_issues_extraction", table_name="validation_issues", schema="docflow"
    )
    op.drop_table("validation_issues", schema="docflow")
