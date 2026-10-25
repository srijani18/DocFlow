"""Upload and document tables (F2 plan §3)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

CONTENT_TYPES = ("application/pdf", "image/png", "image/jpeg")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_CONTENT_TYPE_LIST = ", ".join(f"'{content_type}'" for content_type in CONTENT_TYPES)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


def _timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Upload(Base):
    """A started upload: what the browser declared, and where it may put the bytes."""

    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set when the upload is completed; repeated completions return this document (AC5).
    document_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _timestamp()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"content_type IN ({_CONTENT_TYPE_LIST})", name="content_type"),
        CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_UPLOAD_BYTES}", name="size_bytes"),
        # The real duplicate guard (AC3); the check when an upload starts is a shortcut.
        Index("uq_documents_workspace_sha256", "workspace_id", "sha256", unique=True),
        Index("ix_documents_workspace_created", "workspace_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE")
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.uploads.id"), unique=True)
    storage_path: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()
