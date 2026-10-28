"""Hourly housekeeping across all workspaces (F14 AC11, plan §5), a system operation.

- Files of uploads that were never completed are deleted from storage an hour after the
  upload expired (completing an expired upload is refused, so nothing can still need them).
  Files of documents are never touched: a completed upload has a `document_id`.
- Their upload rows go after 7 days.
- Idempotency keys go after 24 hours (F14 D4).
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.rls_system import system_session
from app.documents.models import Upload
from app.documents.service import upload_path
from app.idempotency.models import KEEP_FOR, IdempotencyKey
from app.storage.client import Storage

log = get_logger(__name__)

INTERVAL_SECONDS = 3600
FILE_GRACE = timedelta(hours=1)
KEEP_UPLOAD_ROWS = timedelta(days=7)
BATCH = 100  # objects per storage delete request


@dataclass(frozen=True)
class Swept:
    files_deleted: int
    uploads_deleted: int
    idempotency_keys_deleted: int


class Maintenance:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: Storage,
        interval_seconds: float = INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._storage = storage
        self._interval = interval_seconds
        self._clock = clock
        self._last: float | None = None

    async def run_if_due(self) -> Swept | None:
        now = self._clock()
        if self._last is not None and now - self._last < self._interval:
            return None
        self._last = now
        swept = await self.run()
        if swept != Swept(0, 0, 0):
            log.info("maintenance_swept", **swept.__dict__)
        return swept

    async def run(self) -> Swept:
        files = 0
        while batch := await self._abandoned_uploads():
            await self._storage.delete([upload_path(ws, upload_id) for upload_id, ws in batch])
            async with system_session(self._sessionmaker) as session, session.begin():
                # tenant-unscoped: housekeeping across all workspaces (system session).
                await session.execute(
                    update(Upload)
                    .where(Upload.id.in_([upload_id for upload_id, _ in batch]))
                    .values(cleaned_at=func.now())
                )
            files += len(batch)
        async with system_session(self._sessionmaker) as session, session.begin():
            # tenant-unscoped: housekeeping across all workspaces (system session).
            uploads = await session.execute(
                delete(Upload).where(
                    Upload.document_id.is_(None),
                    Upload.expires_at < func.now() - KEEP_UPLOAD_ROWS,
                )
            )
            keys = await session.execute(
                delete(IdempotencyKey).where(IdempotencyKey.created_at < func.now() - KEEP_FOR)
            )
        return Swept(files, uploads.rowcount, keys.rowcount)  # type: ignore[attr-defined]

    async def _abandoned_uploads(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        async with system_session(self._sessionmaker) as session:
            # tenant-unscoped: housekeeping across all workspaces (system session).
            rows = await session.execute(
                select(Upload.id, Upload.workspace_id)
                .where(
                    Upload.document_id.is_(None),
                    Upload.cleaned_at.is_(None),
                    Upload.expires_at < func.now() - FILE_GRACE,
                )
                .order_by(Upload.expires_at)
                .limit(BATCH)
            )
            return [(row.id, row.workspace_id) for row in rows]
