"""Upload and document tables (F2 plan §3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

CONTENT_TYPES = ("application/pdf", "image/png", "image/jpeg")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_CONTENT_TYPE_LIST = ", ".join(f"'{content_type}'" for content_type in CONTENT_TYPES)


class DocumentStatus(StrEnum):
    """F3 statuses. F6 adds VALIDATING and APPROVED."""

    UPLOADED = "UPLOADED"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


PROCESSING_STATUSES = frozenset(
    {
        DocumentStatus.UPLOADED,
        DocumentStatus.CLASSIFYING,
        DocumentStatus.EXTRACTING,
        DocumentStatus.VALIDATING,
    }
)
_STATUS_LIST = ", ".join(f"'{status}'" for status in DocumentStatus)


class DocType(StrEnum):
    """F4 classification labels."""

    INVOICE = "invoice"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    OTHER = "other"


_DOC_TYPE_LIST = ", ".join(f"'{doc_type}'" for doc_type in DocType)


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
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status"),
        CheckConstraint(f"doc_type IN ({_DOC_TYPE_LIST})", name="doc_type"),
        CheckConstraint("doc_type_confidence BETWEEN 0 AND 1", name="doc_type_confidence"),
        # The real duplicate guard (AC3); the check when an upload starts is a shortcut.
        Index("uq_documents_workspace_sha256", "workspace_id", "sha256", unique=True),
        Index("ix_documents_workspace_created", "workspace_id", "created_at", "id"),
        Index("ix_documents_workspace_vendor", "workspace_id", "vendor_name"),
        Index("ix_documents_workspace_date", "workspace_id", "document_date"),
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
    # Machine-readable cause, e.g. no_ai_key, so such failures can be requeued (F15 AC8).
    failure_code: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime] = _timestamp()
    doc_type: Mapped[str | None] = mapped_column(Text)
    doc_type_confidence: Mapped[float | None] = mapped_column(REAL)
    # The current extraction version and the fields copied from it for lists and search
    # (ADR-0005 §4, F5 AC7). use_alter: documents and extractions reference each other.
    current_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "docflow.extractions.id", use_alter=True, name="fk_documents_current_extraction_id"
        )
    )
    vendor_name: Mapped[str | None] = mapped_column(Text)
    document_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    # Approval (F6 auto-approval, F7 by a person).
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("docflow.users.id"))
    approved_by_agent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Bumped by each retry, so each processing run has its own job key (F3 plan §3).
    processing_generation: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class DocumentEvent(Base):
    """Every status change, with its time (F3 AC2). Feeds the latency metric."""

    __tablename__ = "document_events"
    __table_args__ = (Index("ix_document_events_document", "document_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.documents.id", ondelete="CASCADE")
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docflow.jobs.id", ondelete="SET NULL")
    )
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
