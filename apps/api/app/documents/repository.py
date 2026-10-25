"""SQL for uploads and documents. Every function takes a WorkspaceScope (constitution §4)."""

import uuid
from datetime import datetime

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, Upload


async def find_document_by_sha256(
    session: AsyncSession, scope: WorkspaceScope, sha256: str
) -> Document | None:
    document: Document | None = await session.scalar(
        select(Document).where(
            Document.workspace_id == scope.workspace_id, Document.sha256 == sha256
        )
    )
    return document


async def insert_upload(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    expires_at: datetime,
) -> Upload:
    upload = Upload(
        workspace_id=scope.workspace_id,
        created_by_user_id=scope.user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        expires_at=expires_at,
    )
    session.add(upload)
    await session.flush()
    return upload


async def lock_upload(
    session: AsyncSession, scope: WorkspaceScope, upload_id: uuid.UUID
) -> Upload | None:
    """The upload row, locked until commit, so concurrent completions run one at a time."""
    upload: Upload | None = await session.scalar(
        select(Upload)
        .where(Upload.workspace_id == scope.workspace_id, Upload.id == upload_id)
        .with_for_update()
    )
    return upload


async def insert_document_if_new(
    session: AsyncSession, scope: WorkspaceScope, upload: Upload, *, storage_path: str, status: str
) -> Document | None:
    """Insert the document, or return None if this content is already a document (AC3)."""
    statement = (
        pg_insert(Document)
        .values(
            workspace_id=scope.workspace_id,
            upload_id=upload.id,
            storage_path=storage_path,
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            status=status,
            created_by_user_id=scope.user_id,
        )
        .on_conflict_do_nothing()
        .returning(Document)
    )
    document: Document | None = await session.scalar(statement)
    return document


async def mark_upload_completed(
    session: AsyncSession, scope: WorkspaceScope, upload_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    await session.execute(
        update(Upload)
        .where(Upload.workspace_id == scope.workspace_id, Upload.id == upload_id)
        .values(document_id=document_id)
    )


async def get_document(
    session: AsyncSession, scope: WorkspaceScope, document_id: uuid.UUID
) -> Document | None:
    document: Document | None = await session.scalar(
        select(Document).where(
            Document.workspace_id == scope.workspace_id, Document.id == document_id
        )
    )
    return document


async def list_documents(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    before: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[Document]:
    """Newest first. `before` is the (created_at, id) of the last row of the previous page."""
    statement = select(Document).where(Document.workspace_id == scope.workspace_id)
    if before is not None:
        statement = statement.where(tuple_(Document.created_at, Document.id) < before)
    statement = statement.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)
    return list(await session.scalars(statement))
