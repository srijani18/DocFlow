"""Versioned, append-only extractions (ADR-0005, F5 plan §3)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SOURCES = ("model", "agent_fix", "human")


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        CheckConstraint("source IN ('model', 'agent_fix', 'human')", name="source"),
        Index("uq_extractions_document_version", "document_id", "version", unique=True),
        # One model extraction per processing run, so a re-run can't store a second (AC5).
        Index(
            "uq_extractions_model_run",
            "document_id",
            "processing_generation",
            unique=True,
            postgresql_where=text("source = 'model'"),
        ),
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
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    schema_id: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confidence: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    prompt_version: Mapped[str | None] = mapped_column(Text)
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docflow.llm_calls.id", ondelete="SET NULL")
    )
    processing_generation: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
