"""Validation issues per extraction version (F6 plan §3)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('error', 'warning', 'info')", name="severity"),
        Index("ix_validation_issues_extraction", "extraction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.documents.id", ondelete="CASCADE")
    )
    # The extraction version the issue was found on (or resolved for).
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.extractions.id", ondelete="CASCADE")
    )
    check_name: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    paths: Mapped[list[str]] = mapped_column(ARRAY(Text))
    message: Mapped[str] = mapped_column(Text)
    fixed_by_agent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
