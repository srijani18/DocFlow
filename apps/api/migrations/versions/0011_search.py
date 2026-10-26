"""Search: keyword index on documents, and one embedding per document (F8 plan §2).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_embeddings",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["docflow.documents.id"],
            name=op.f("fk_document_embeddings_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["docflow.extractions.id"],
            name=op.f("fk_document_embeddings_extraction_id_extractions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["docflow.workspaces.id"],
            name=op.f("fk_document_embeddings_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_document_embeddings")),
        schema="docflow",
    )
    op.create_index(
        "ix_document_embeddings_hnsw",
        "document_embeddings",
        ["embedding"],
        unique=False,
        schema="docflow",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_document_embeddings_workspace_id"),
        "document_embeddings",
        ["workspace_id"],
        unique=False,
        schema="docflow",
    )
    op.add_column(
        "documents",
        sa.Column("search_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        schema="docflow",
    )
    op.add_column(
        "documents",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, "
                "regexp_replace(filename, '[^[:alnum:]]+', ' ', 'g') || ' ' || search_text)",
                persisted=True,
            ),
            nullable=False,
        ),
        schema="docflow",
    )
    op.create_index(
        "ix_documents_search",
        "documents",
        ["search_vector"],
        unique=False,
        schema="docflow",
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_index(
        "ix_documents_search", table_name="documents", schema="docflow", postgresql_using="gin"
    )
    op.drop_column("documents", "search_vector", schema="docflow")
    op.drop_column("documents", "search_text", schema="docflow")
    op.drop_index(
        op.f("ix_document_embeddings_workspace_id"),
        table_name="document_embeddings",
        schema="docflow",
    )
    op.drop_index(
        "ix_document_embeddings_hnsw",
        table_name="document_embeddings",
        schema="docflow",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("document_embeddings", schema="docflow")
