"""Seeding and inspection helpers for queue and pipeline tests (real commits)."""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import create_sessionmaker
from app.core.tenancy import WorkspaceScope
from app.documents import service
from app.documents.models import Document, DocumentEvent
from app.jobs.models import Job
from app.llm.models import LlmCall
from app.storage.fake import FakeStorage
from tests.support.clock import FrozenClock
from tests.support.documents import PDF
from tests.support.identity import TwoWorkspaces, make_two_workspaces


@dataclass
class Recorder:
    """Stands in for the event broker."""

    events: list[service.StatusEvent] = field(default_factory=list)

    def publish(self, event: service.StatusEvent) -> None:
        self.events.append(event)

    @property
    def statuses(self) -> list[str]:
        return [event.status for event in self.events]


@dataclass
class Seeded:
    workspaces: TwoWorkspaces
    scope: WorkspaceScope
    sessionmaker: async_sessionmaker[AsyncSession]


async def seed_workspaces(engine: AsyncEngine) -> Seeded:
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session, session.begin():
        w = await make_two_workspaces(session)
    scope = WorkspaceScope(workspace_id=w.a.id, user_id=w.a_admin.id, role="admin")
    return Seeded(w, scope, sessionmaker)


async def seed_document(seeded: Seeded, storage: FakeStorage, data: bytes = PDF) -> uuid.UUID:
    """A completed upload: document UPLOADED plus its queued job, committed."""
    clock = FrozenClock()
    async with seeded.sessionmaker() as session, session.begin():
        new = await service.start_upload(
            session,
            storage,
            clock,
            seeded.scope,
            filename="invoice.pdf",
            content_type="application/pdf",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    assert isinstance(new, service.NewUpload)
    storage.put(new.signed.path, data)
    async with seeded.sessionmaker() as session, session.begin():
        document, _ = await service.complete_upload(
            session, storage, clock, seeded.scope, str(new.upload.id)
        )
    return document.id


async def document_row(seeded: Seeded, document_id: uuid.UUID) -> Document:
    async with seeded.sessionmaker() as session:
        return (await session.scalars(select(Document).where(Document.id == document_id))).one()


async def jobs_for(
    seeded: Seeded, document_id: uuid.UUID, kind: str = "process_document"
) -> list[Job]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(Job)
            .where(Job.document_id == document_id, Job.kind == kind)
            .order_by(Job.created_at)
        )
        return list(rows)


async def events_for(seeded: Seeded, document_id: uuid.UUID) -> list[tuple[str | None, str]]:
    async with seeded.sessionmaker() as session:
        rows = await session.execute(
            select(DocumentEvent.from_status, DocumentEvent.to_status)
            .where(DocumentEvent.document_id == document_id)
            .order_by(DocumentEvent.id)
        )
        return [(row.from_status, row.to_status) for row in rows]


async def make_due_now(seeded: Seeded) -> None:
    """Skip the backoff wait: every queued job becomes due."""
    async with seeded.sessionmaker() as session, session.begin():
        await session.execute(
            update(Job).where(Job.status == "queued").values(run_after=Job.created_at)
        )


async def wait_for_status(seeded: Seeded, document_id: uuid.UUID, status: str) -> None:
    """Poll until the document reaches `status` (for tests driving the real worker loop)."""
    for _ in range(200):
        if (await document_row(seeded, document_id)).status == status:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"document never reached {status}")


async def llm_calls_for(seeded: Seeded, document_id: uuid.UUID) -> list[LlmCall]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(LlmCall).where(LlmCall.document_id == document_id).order_by(LlmCall.created_at)
        )
        return list(rows)
