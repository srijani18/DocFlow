"""API models for uploads and documents (F2 plan §2)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.documents.models import MAX_UPLOAD_BYTES, DocType, DocumentStatus


class ContentType(StrEnum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"


class UploadStart(BaseModel):
    """What the browser declares before uploading. Checked again at completion (AC4)."""

    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_type: ContentType
    size_bytes: int = Field(ge=1, le=MAX_UPLOAD_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Lowercase hex SHA-256 of the file")


class Document(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: ContentType
    size_bytes: int
    sha256: str
    status: DocumentStatus
    status_changed_at: datetime
    failure_reason: str | None
    failure_code: str | None = Field(description="Machine-readable cause, e.g. no_ai_key (F15)")
    doc_type: DocType | None = Field(description="Set by classification (F4)")
    doc_type_confidence: float | None
    vendor_name: str | None = Field(description="From the current extraction (F5)")
    document_date: date | None
    total_amount: Decimal | None = Field(description="Exact decimal, serialised as a string")
    currency: str | None
    created_at: datetime
    updated_at: datetime


class UploadTicket(BaseModel):
    """A new upload: PUT the bytes to `bucket`/`path` with `token`, then complete it."""

    kind: Literal["upload"] = "upload"
    upload_id: uuid.UUID
    bucket: str
    path: str
    token: str
    expires_at: datetime


class UploadDuplicate(BaseModel):
    """The same content is already a document in this workspace (AC3). Nothing to upload."""

    kind: Literal["duplicate"] = "duplicate"
    document: Document


UploadStartResult = Annotated[UploadTicket | UploadDuplicate, Field(discriminator="kind")]


class DocumentPage(BaseModel):
    items: list[Document]
    next_cursor: str | None


class FileUrl(BaseModel):
    url: str
    expires_at: datetime


class DocumentStatusEvent(BaseModel):
    """The `data` of a `document.status` server-sent event (F3 plan §2)."""

    document_id: uuid.UUID
    status: DocumentStatus
    failure_reason: str | None
    changed_at: datetime
