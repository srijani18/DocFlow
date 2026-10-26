"""Workspaces' own AI provider keys, encrypted (F15 plan §2, ADR-0008)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

PROVIDERS = ("gemini", "groq", "openrouter")
STATUSES = ("ok", "rejected", "unchecked")


class WorkspaceAiKey(Base):
    __tablename__ = "workspace_ai_keys"
    __table_args__ = (
        CheckConstraint("provider IN ('gemini', 'groq', 'openrouter')", name="provider"),
        CheckConstraint("status IN ('ok', 'rejected', 'unchecked')", name="status"),
    )

    # The primary key leads with workspace_id: one key per provider per workspace.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer)
    last4: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
