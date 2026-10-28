"""Mark uploads whose file was deleted because they were never completed (F14 AC11).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "uploads",
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        schema="docflow",
    )


def downgrade() -> None:
    # Constitution §7.1: every migration must be reversible.
    op.drop_column("uploads", "cleaned_at", schema="docflow")
