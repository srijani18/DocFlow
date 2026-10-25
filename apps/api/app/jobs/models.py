"""The job queue table (ADR-0001, F3 plan §3)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

JOB_KINDS = ("process_document",)
JOB_STATUSES = ("queued", "running", "succeeded", "dead")
DEFAULT_MAX_ATTEMPTS = 5


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('process_document')", name="kind"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'dead')", name="status"),
        Index(
            "ix_jobs_claimable",
            "run_after",
            postgresql_where=text("status IN ('queued', 'running')"),
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
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(
        Integer, server_default=text(str(DEFAULT_MAX_ATTEMPTS))
    )
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    # process_document:{document_id}:{generation}: one job per processing run (AC8).
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
