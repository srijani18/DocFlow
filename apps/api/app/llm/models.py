"""Every LLM call, successful or not (constitution §5.2, F4 plan §3)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

OUTCOMES = ("ok", "error", "invalid_output", "cache_hit", "skipped")


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('ok', 'error', 'invalid_output', 'cache_hit', 'skipped')", name="outcome"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docflow.documents.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docflow.jobs.id", ondelete="SET NULL")
    )
    task: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer)
    # F10: where in the task's route this attempt was, and how the file was sent.
    route_position: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    fallback: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    input_mode: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCacheEntry(Base):
    """A validated answer, reused for an identical request in the same workspace (F10 AC6)."""

    __tablename__ = "llm_cache"

    # sha256 of (workspace, task, prompt version, request content, schema, route)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    task: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text)
    source_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docflow.llm_calls.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
