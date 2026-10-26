"""Job worker loop (F3 plan §1, overview §5).

One job at a time (F3 spec D3). While idle the worker waits on an in-process wake event,
until the next retry is due, or until the 5-minute sweep, whichever comes first. It never
polls the database every few seconds (constitution §9.3, F3 AC11).
"""

import asyncio
import os
import socket
import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.documents import service as documents
from app.jobs import repository as queue
from app.jobs.backoff import backoff_seconds
from app.jobs.errors import PermanentError, StepError, TransientError

log = get_logger(__name__)

SWEEP_SECONDS = 300.0
# After an unexpected failure of the loop itself (e.g. the database is down), wait this
# long before trying again rather than spinning.
LOOP_ERROR_PAUSE_SECONDS = 5.0
UNEXPECTED_REASON = "Processing failed unexpectedly"


class Runner(Protocol):
    async def run(
        self, *, workspace_id: uuid.UUID, document_id: uuid.UUID, job_id: uuid.UUID, attempt: int
    ) -> None: ...


class Publisher(Protocol):
    def publish(self, event: documents.StatusEvent) -> None: ...


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


class Worker:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        pipeline: Runner,
        events: Publisher,
        sweep_seconds: float = SWEEP_SECONDS,
        worker_id: str | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._pipeline = pipeline
        self._events = events
        self._sweep_seconds = sweep_seconds
        self.worker_id = worker_id or default_worker_id()
        self._wake_event = asyncio.Event()
        self.jobs_run = 0

    def wake(self) -> None:
        """Called by the API after committing a new job (same process, ROLE=all)."""
        self._wake_event.set()

    async def run(self) -> None:
        log.info("worker_started", worker_id=self.worker_id)
        while True:
            try:
                await self.drain()  # also picks up jobs left over from before a restart (AC12)
                timeout = await self._seconds_until_next_due()
            except Exception:
                log.exception("worker_loop_error")
                timeout = LOOP_ERROR_PAUSE_SECONDS
            try:
                async with asyncio.timeout(timeout):
                    await self._wake_event.wait()
            except TimeoutError:
                pass
            self._wake_event.clear()

    async def drain(self) -> int:
        """Run every job that is due now. Returns how many ran."""
        ran = 0
        while (job := await self._claim()) is not None:
            await self._run_job(job)
            ran += 1
        return ran

    async def _claim(self) -> queue.ClaimedJob | None:
        async with self._sessionmaker() as session, session.begin():
            return await queue.claim(session, worker_id=self.worker_id)

    async def _seconds_until_next_due(self) -> float:
        async with self._sessionmaker() as session:
            due = await queue.seconds_until_next_due(session)
        return self._sweep_seconds if due is None else min(due, self._sweep_seconds)

    async def _run_job(self, job: queue.ClaimedJob) -> None:
        bound = log.bind(job_id=str(job.id), document_id=str(job.document_id), attempt=job.attempts)
        self.jobs_run += 1
        try:
            await self._pipeline.run(
                workspace_id=job.workspace_id,
                document_id=job.document_id,
                job_id=job.id,
                attempt=job.attempts,
            )
        except PermanentError as exc:
            bound.warning("job_failed_permanently", reason=exc.reason, detail=exc.detail)
            await self._give_up(job, exc)
        except StepError as exc:
            await self._retry_or_give_up(job, exc)
        except Exception as exc:
            # Unknown errors are treated as transient, so a bug can't fail a document
            # permanently without the record of 5 attempts (F3 plan §4).
            bound.exception("job_crashed")
            await self._retry_or_give_up(job, TransientError(UNEXPECTED_REASON, detail=repr(exc)))
        else:
            async with self._sessionmaker() as session, session.begin():
                await queue.mark_succeeded(session, job.id, worker_id=self.worker_id)
            bound.info("job_succeeded")

    async def _retry_or_give_up(self, job: queue.ClaimedJob, exc: StepError) -> None:
        if job.attempts >= job.max_attempts:
            log.warning("job_dead", job_id=str(job.id), reason=exc.reason, detail=exc.detail)
            await self._give_up(job, exc, reason=f"{exc.reason} after {job.attempts} attempts")
            return
        retry_after = exc.retry_after_seconds if isinstance(exc, TransientError) else None
        delay = backoff_seconds(job.attempts, retry_after_seconds=retry_after)
        log.info(
            "job_retry_scheduled",
            job_id=str(job.id),
            reason=exc.reason,
            detail=exc.detail,
            delay_seconds=round(delay, 1),
        )
        async with self._sessionmaker() as session, session.begin():
            await queue.retry_later(
                session, job.id, worker_id=self.worker_id, delay_seconds=delay, error=exc.detail
            )

    async def _give_up(
        self, job: queue.ClaimedJob, exc: StepError, *, reason: str | None = None
    ) -> None:
        event = None
        async with self._sessionmaker() as session, session.begin():
            if await queue.mark_dead(session, job.id, worker_id=self.worker_id, error=exc.detail):
                loaded = await documents.load_for_job(
                    session, workspace_id=job.workspace_id, document_id=job.document_id
                )
                if loaded is not None:
                    event = await documents.fail(
                        session,
                        loaded[0],
                        job.document_id,
                        reason=reason or exc.reason,
                        job_id=job.id,
                        detail=exc.detail,
                        code=exc.code,
                    )
        if event is not None:
            self._events.publish(event)
