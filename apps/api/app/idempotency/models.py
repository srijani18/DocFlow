"""Stored outcomes of write requests sent with an Idempotency-Key (F14 plan §3)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# A key protects against repeats for this long (F14 AC6).
KEEP_FOR = timedelta(hours=24)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done')", name="status"),
        Index("uq_idempotency_keys_key", "workspace_id", "user_id", "key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    # sha256 of method, path and body: the same key with a different request is refused.
    request_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'running'"))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_type: Mapped[str | None] = mapped_column(Text)
    response_body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
