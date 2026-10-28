"""Review: corrections per changed field, and the approved extraction version (F7 plan §2).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column(
            "old_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "new_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_corrections_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["docflow.extractions.id"],
            name=op.f("fk_corrections_extraction_id_extractions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["docflow.users.id"], name=op.f("fk_corrections_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_corrections_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_corrections")),
        schema="docflow",
    )
    op.create_index(
        "ix_corrections_document", "corrections", ["document_id"], unique=False, schema="docflow"
    )
    op.create_index(
        op.f("ix_corrections_workspace_id"),
        "corrections",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column(
        "documents", sa.Column("approved_extraction_id", sa.Uuid(), nullable=True), schema="docflow"
    )
    op.create_foreign_key(
        "fk_documents_approved_extraction_id",
        "documents",
        "extractions",
        ["approved_extraction_id"],
        ["id"],
        source_schema="docflow",
        referent_schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_constraint(
        "fk_documents_approved_extraction_id", "documents", schema="docflow", type_="foreignkey"
    )
    op.drop_column("documents", "approved_extraction_id", schema="docflow")
    op.drop_index(op.f("ix_corrections_workspace_id"), table_name="corrections", schema="docflow")
    op.drop_index("ix_corrections_document", table_name="corrections", schema="docflow")
    op.drop_table("corrections", schema="docflow")
