"""Documents: uploads and documents (F2 plan §3).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["docflow.users.id"],
            name=op.f("fk_uploads_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_uploads_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
        schema="docflow",
    )
    op.create_index(
        op.f("ix_uploads_workspace_id"), "uploads", ["workspace_id"], unique=False, schema="docflow"
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
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
            "content_type IN ('application/pdf', 'image/png', 'image/jpeg')",
            name=op.f("ck_documents_content_type"),
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name=op.f("ck_documents_size_bytes")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["docflow.users.id"],
            name=op.f("fk_documents_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["docflow.uploads.id"], name=op.f("fk_documents_upload_id_uploads")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_documents_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("upload_id", name=op.f("uq_documents_upload_id")),
        schema="docflow",
    )
    op.create_index(
        "ix_documents_workspace_created",
        "documents",
        ["workspace_id", "created_at", "id"],
        unique=False,
        schema="docflow",
    )
    op.create_index(
        "uq_documents_workspace_sha256",
        "documents",
        ["workspace_id", "sha256"],
        unique=True,
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_index("uq_documents_workspace_sha256", table_name="documents", schema="docflow")
    op.drop_index("ix_documents_workspace_created", table_name="documents", schema="docflow")
    op.drop_table("documents", schema="docflow")
    op.drop_index(op.f("ix_uploads_workspace_id"), table_name="uploads", schema="docflow")
    op.drop_table("uploads", schema="docflow")
