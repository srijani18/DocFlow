"""Queue SQL (ADR-0001, F3 plan §4). The database clock (now()) is the only clock here,
so leases and delays mean the same thing to every worker."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.jobs.models import Job

LEASE = timedelta(minutes=5)  # F3 spec D2
PROCESS_DOCUMENT = "process_document"
EMBED_DOCUMENT = "embed_document"  # F8: search embedding of the current extraction


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    kind: str
    workspace_id: uuid.UUID
    document_id: uuid.UUID
    attempts: int
    max_attempts: int


async def enqueue(
    session: AsyncSession, scope: WorkspaceScope, *, document_id: uuid.UUID, generation: int
) -> uuid.UUID | None:
    """Queue processing for one run of a document; None if that run is already queued."""
    job_id: uuid.UUID | None = await session.scalar(
        pg_insert(Job)
        .values(
            workspace_id=scope.workspace_id,
            document_id=document_id,
            kind=PROCESS_DOCUMENT,
            idempotency_key=f"{PROCESS_DOCUMENT}:{document_id}:{generation}",
        )
        .on_conflict_do_nothing(index_elements=[Job.idempotency_key])
        .returning(Job.id)
    )
    return job_id


async def enqueue_embedding(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
) -> uuid.UUID | None:
    """Queue embedding of one extraction version; None if it's already queued (F8 AC6)."""
    job_id: uuid.UUID | None = await session.scalar(
        pg_insert(Job)
        .values(
            workspace_id=scope.workspace_id,
            document_id=document_id,
            kind=EMBED_DOCUMENT,
            idempotency_key=f"{EMBED_DOCUMENT}:{extraction_id}",
        )
        .on_conflict_do_nothing(index_elements=[Job.idempotency_key])
        .returning(Job.id)
    )
    return job_id


def _claimable() -> object:
    return or_(
        (Job.status == "queued") & (Job.run_after <= func.now()),
        # A worker that crashed mid-job leaves an expired lease behind (AC5).
        (Job.status == "running") & (Job.locked_until < func.now()),
    )


async def claim(session: AsyncSession, *, worker_id: str) -> ClaimedJob | None:
    """Lease the next due job. SKIP LOCKED lets concurrent claimers pass each other."""
    # tenant-unscoped: the worker serves every workspace; each job carries its own.
    next_id = (
        select(Job.id)
        .where(_claimable())  # type: ignore[arg-type]
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            update(Job)
            .where(Job.id == next_id)
            .values(
                status="running",
                attempts=Job.attempts + 1,
                locked_until=func.now() + LEASE,
                locked_by=worker_id,
                updated_at=func.now(),
            )
            .returning(
                Job.id, Job.kind, Job.workspace_id, Job.document_id, Job.attempts, Job.max_attempts
            )
        )
    ).first()
    if row is None:
        return None
    return ClaimedJob(
        row.id, row.kind, row.workspace_id, row.document_id, row.attempts, row.max_attempts
    )


async def _finish(
    session: AsyncSession, job_id: uuid.UUID, worker_id: str, **values: object
) -> bool:
    """Update a job only while this worker still holds it (AC5: a worker whose lease was
    taken over must not overwrite the new owner's outcome)."""
    # tenant-unscoped: keyed by the job this worker claimed.
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id, Job.status == "running")
        .values(updated_at=func.now(), **values)
        .returning(Job.id)
    )
    return result.first() is not None


async def mark_succeeded(session: AsyncSession, job_id: uuid.UUID, *, worker_id: str) -> bool:
    return await _finish(
        session, job_id, worker_id, status="succeeded", finished_at=func.now(), locked_until=None
    )


async def retry_later(
    session: AsyncSession, job_id: uuid.UUID, *, worker_id: str, delay_seconds: float, error: str
) -> bool:
    return await _finish(
        session,
        job_id,
        worker_id,
        status="queued",
        run_after=func.now() + timedelta(seconds=delay_seconds),
        locked_until=None,
        locked_by=None,
        last_error=error,
    )


async def mark_dead(
    session: AsyncSession, job_id: uuid.UUID, *, worker_id: str, error: str
) -> bool:
    return await _finish(
        session,
        job_id,
        worker_id,
        status="dead",
        finished_at=func.now(),
        locked_until=None,
        last_error=error,
    )


async def seconds_until_next_due(session: AsyncSession) -> float | None:
    """When the earliest queued job or expired lease becomes claimable; None if no work."""
    # tenant-unscoped: the worker's own scheduling, across all workspaces.
    due = func.least(
        select(func.min(Job.run_after)).where(Job.status == "queued").scalar_subquery(),
        select(func.min(Job.locked_until)).where(Job.status == "running").scalar_subquery(),
    )
    seconds = await session.scalar(select(func.extract("epoch", due - func.now())))
    return None if seconds is None else max(float(seconds), 0.0)
