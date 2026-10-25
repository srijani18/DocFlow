"""Runs one document through the pipeline (F3 plan §1).

The document's status is the pipeline's checkpoint. Each step stores its result and moves
the status forward in one transaction, so a re-run (crash, retry, duplicate job) resumes
at the first unfinished step and never stores a result twice (AC5, AC6).
"""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents
from app.documents.models import PROCESSING_STATUSES, DocumentStatus
from app.jobs.errors import PermanentError, TransientError
from app.storage.client import Storage, StorageUnavailableError

log = get_logger(__name__)

Publish = Callable[[documents.StatusEvent], None]
Writer = Callable[[AsyncSession], Awaitable[None]]


@dataclass
class StepContext:
    """What a step gets: the verified file and a way to commit its result."""

    scope: WorkspaceScope
    document_id: uuid.UUID
    content_type: str
    file: bytes
    job_id: uuid.UUID
    attempt: int
    sessionmaker: async_sessionmaker[AsyncSession]
    publish: Publish

    async def advance(
        self,
        *,
        from_status: DocumentStatus,
        to: DocumentStatus,
        write: Writer | None = None,
        detail: str | None = None,
    ) -> None:
        """Store the step's result (`write`) and move the status on, atomically."""
        async with self.sessionmaker() as session, session.begin():
            if write is not None:
                await write(session)
            _, event = await documents.transition(
                session,
                self.scope,
                self.document_id,
                expected=[from_status],
                to=to,
                job_id=self.job_id,
                detail=detail,
            )
        self.publish(event)


Step = Callable[[StepContext], Awaitable[None]]


async def skip_classification(ctx: StepContext) -> None:
    """Placeholder until F4: no classification yet."""
    await ctx.advance(from_status=DocumentStatus.CLASSIFYING, to=DocumentStatus.EXTRACTING)


async def skip_extraction(ctx: StepContext) -> None:
    """Placeholder until F5: no extraction yet."""
    await ctx.advance(from_status=DocumentStatus.EXTRACTING, to=DocumentStatus.NEEDS_REVIEW)


class Pipeline:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: Storage,
        publish: Publish,
        classify: Step = skip_classification,
        extract: Step = skip_extraction,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._storage = storage
        self._publish = publish
        self._steps: dict[DocumentStatus, Step] = {
            DocumentStatus.CLASSIFYING: classify,
            DocumentStatus.EXTRACTING: extract,
        }

    async def run(
        self, *, workspace_id: uuid.UUID, document_id: uuid.UUID, job_id: uuid.UUID, attempt: int
    ) -> None:
        async with self._sessionmaker() as session:
            loaded = await documents.load_for_job(
                session, workspace_id=workspace_id, document_id=document_id
            )
        if loaded is None:
            raise PermanentError("Document not found", detail=f"document {document_id} is gone")
        scope, document = loaded
        if document.status not in PROCESSING_STATUSES:
            log.info("pipeline_nothing_to_do", status=document.status)
            return

        file = await self._fetch(document.storage_path, expected_sha256=document.sha256)
        ctx = StepContext(
            scope=scope,
            document_id=document_id,
            content_type=document.content_type,
            file=file,
            job_id=job_id,
            attempt=attempt,
            sessionmaker=self._sessionmaker,
            publish=self._publish,
        )
        status = DocumentStatus(document.status)
        if status is DocumentStatus.UPLOADED:
            await ctx.advance(from_status=status, to=DocumentStatus.CLASSIFYING)
            status = DocumentStatus.CLASSIFYING
        while (step := self._steps.get(status)) is not None:
            await step(ctx)
            status = await self._current_status(scope, document_id)

    async def _fetch(self, path: str, *, expected_sha256: str) -> bytes:
        try:
            data = await self._storage.download(path)
        except StorageUnavailableError as exc:
            raise TransientError("File storage unavailable", detail=str(exc)) from exc
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            # The stored bytes aren't what was uploaded and hashed (F3 AC7).
            raise PermanentError("File integrity check failed", detail="sha256 mismatch")
        return data

    async def _current_status(
        self, scope: WorkspaceScope, document_id: uuid.UUID
    ) -> DocumentStatus:
        async with self._sessionmaker() as session:
            loaded = await documents.load_for_job(
                session, workspace_id=scope.workspace_id, document_id=document_id
            )
        if loaded is None:
            raise PermanentError("Document not found")
        return DocumentStatus(loaded[1].status)
