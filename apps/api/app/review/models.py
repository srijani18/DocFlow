"""One row per field a reviewer changed (F7 plan §2)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Correction(Base):
    __tablename__ = "corrections"
    __table_args__ = (Index("ix_corrections_document", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.documents.id", ondelete="CASCADE")
    )
    # The human version the change produced.
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.extractions.id", ondelete="CASCADE")
    )
    path: Mapped[str] = mapped_column(Text)
    old_value: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    new_value: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
