import asyncio
from typing import Any

import pytest
from sqlalchemy import event, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents import service
from app.documents.models import DocumentStatus
from app.jobs.errors import PermanentError, TransientError
from app.jobs.models import Job
from app.pipeline.runner import Pipeline, StepContext, skip_classification, skip_extraction
from app.storage.fake import FakeStorage
from app.worker.loop import Worker
from tests.support.documents import PDF
from tests.support.pipeline import (
    Recorder,
    Seeded,
    document_row,
    events_for,
    jobs_for,
    make_due_now,
    seed_document,
    seed_workspaces,
    wait_for_status,
)


def make_worker(
    seeded: Seeded, storage: FakeStorage, recorder: Recorder, **steps: object
) -> Worker:
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=recorder.publish,
        **steps,  # type: ignore[arg-type]
    )
    return Worker(
        sessionmaker=seeded.sessionmaker, pipeline=pipeline, events=recorder, worker_id="test"
    )


async def test_ac1_completed_upload_is_processed(committing_engine: AsyncEngine) -> None:
    seeded, storage, recorder = await seed_workspaces(committing_engine), FakeStorage(), Recorder()
    document_id = await seed_document(seeded, storage)

    ran = await make_worker(seeded, storage, recorder).drain()

    assert ran == 1
    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    assert recorder.statuses == ["CLASSIFYING", "EXTRACTING", "VALIDATING", "NEEDS_REVIEW"]
    assert [job.status for job in await jobs_for(seeded, document_id)] == ["succeeded"]


async def test_ac2_transition_records_event_and_timestamp(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)

    await make_worker(seeded, storage, Recorder()).drain()

    assert await events_for(seeded, document_id) == [
        (None, "UPLOADED"),
        ("UPLOADED", "CLASSIFYING"),
        ("CLASSIFYING", "EXTRACTING"),
        ("EXTRACTING", "VALIDATING"),
        ("VALIDATING", "NEEDS_REVIEW"),
    ]
    document = await document_row(seeded, document_id)
    assert document.status_changed_at >= document.created_at


async def test_ac2_transition_from_wrong_status_rejected(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    document_id = await seed_document(seeded, FakeStorage())

    async with seeded.sessionmaker() as session, session.begin():
        with pytest.raises(service.StatusConflictError):
            await service.transition(
                session,
                seeded.scope,
                document_id,
                expected=[DocumentStatus.EXTRACTING],
                to=DocumentStatus.NEEDS_REVIEW,
            )

    assert (await document_row(seeded, document_id)).status == "UPLOADED"
    assert await events_for(seeded, document_id) == [(None, "UPLOADED")]


async def test_ac7_hash_mismatch_fails_permanently(committing_engine: AsyncEngine) -> None:
    seeded, storage, recorder = await seed_workspaces(committing_engine), FakeStorage(), Recorder()
    document_id = await seed_document(seeded, storage)
    path = next(iter(storage.objects))
    storage.put(path, b"X" * len(PDF))  # same size, different content

    await make_worker(seeded, storage, recorder).drain()

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason) == ("FAILED", "File integrity check failed")
    [job] = await jobs_for(seeded, document_id)
    assert (job.status, job.attempts) == ("dead", 1)
    assert recorder.statuses == ["FAILED"]


async def test_ac4_permanent_error_no_retry(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)

    async def unreadable(ctx: StepContext) -> None:
        raise PermanentError("The file couldn't be read")

    await make_worker(seeded, storage, Recorder(), classify=unreadable).drain()

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason) == ("FAILED", "The file couldn't be read")
    [job] = await jobs_for(seeded, document_id)
    assert (job.status, job.attempts) == ("dead", 1)


async def test_ac3_dead_after_five_attempts(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    calls = 0

    async def flaky(ctx: StepContext) -> None:
        nonlocal calls
        calls += 1
        raise TransientError("AI service unavailable", detail="503 from provider")

    worker = make_worker(seeded, storage, Recorder(), classify=flaky)
    for attempt in range(1, 6):
        assert await worker.drain() == 1
        [job] = await jobs_for(seeded, document_id)
        if attempt < 5:
            assert (job.status, job.attempts, job.last_error) == (
                "queued",
                attempt,
                "503 from provider",
            )
            assert (await document_row(seeded, document_id)).status == "CLASSIFYING"
            assert await worker.drain() == 0  # not due yet: backoff
            await make_due_now(seeded)

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason) == (
        "FAILED",
        "AI service unavailable after 5 attempts",
    )
    assert (job.status, job.attempts) == ("dead", 5)
    assert calls == 5


async def test_ac6_rerun_skips_finished_steps(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    classify_calls = 0
    extract_calls = 0

    async def classify(ctx: StepContext) -> None:
        nonlocal classify_calls
        classify_calls += 1
        await skip_classification(ctx)

    async def extract_once_failing(ctx: StepContext) -> None:
        nonlocal extract_calls
        extract_calls += 1
        if extract_calls == 1:
            raise TransientError("AI service unavailable")
        await skip_extraction(ctx)

    worker = make_worker(
        seeded, storage, Recorder(), classify=classify, extract=extract_once_failing
    )
    await worker.drain()
    await make_due_now(seeded)
    await worker.drain()

    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    assert (classify_calls, extract_calls) == (1, 2)


async def test_unexpected_exception_counts_as_transient(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)

    async def buggy(ctx: StepContext) -> None:
        raise KeyError("bug")

    await make_worker(seeded, storage, Recorder(), classify=buggy).drain()

    [job] = await jobs_for(seeded, document_id)
    assert (job.status, job.attempts) == ("queued", 1)
    assert "KeyError" in (job.last_error or "")


async def test_f16_crashed_job_is_reported_with_its_ids(
    committing_engine: AsyncEngine, sentry_events: list[dict[str, Any]]
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)

    async def buggy(ctx: StepContext) -> None:
        raise KeyError("bug")

    await make_worker(seeded, storage, Recorder(), classify=buggy).drain()

    [job] = await jobs_for(seeded, document_id)
    document = await document_row(seeded, document_id)
    [event] = sentry_events
    assert event["tags"] == {
        "workspace_id": str(document.workspace_id),
        "document_id": str(document_id),
        "job_id": str(job.id),
        "kind": "process_document",
    }
    assert event["exception"]["values"][0]["type"] == "KeyError"


async def test_f16_expected_failures_are_not_reported(
    committing_engine: AsyncEngine, sentry_events: list[dict[str, Any]]
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    await seed_document(seeded, storage)

    async def unavailable(ctx: StepContext) -> None:
        raise TransientError("The AI provider is busy")

    await make_worker(seeded, storage, Recorder(), classify=unavailable).drain()

    assert sentry_events == []


async def test_ac12_queued_jobs_run_after_restart(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)  # queued while "no worker was running"

    task = asyncio.create_task(make_worker(seeded, storage, Recorder()).run())
    try:
        await wait_for_status(seeded, document_id, "NEEDS_REVIEW")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_ac11_idle_worker_runs_no_queries(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    statements: list[str] = []

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    worker = make_worker(seeded, storage, Recorder())
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.2)  # startup: drain once, ask when the next job is due, then idle
    event.listen(committing_engine.sync_engine, "before_cursor_execute", count)
    try:
        await asyncio.sleep(0.5)
        idle_statements = list(statements)

        document_id = await seed_document(seeded, storage)
        worker.wake()
        await wait_for_status(seeded, document_id, "NEEDS_REVIEW")
    finally:
        event.remove(committing_engine.sync_engine, "before_cursor_execute", count)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert idle_statements == []
    assert any("FOR UPDATE SKIP LOCKED" in statement for statement in statements)


async def test_job_for_finished_document_does_nothing(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker = make_worker(seeded, storage, Recorder())
    await worker.drain()
    async with seeded.sessionmaker() as session, session.begin():
        await session.execute(
            insert(Job).values(
                workspace_id=seeded.scope.workspace_id,
                document_id=document_id,
                kind="process_document",
                idempotency_key="duplicate-run",
            )
        )

    assert await worker.drain() == 1
    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    async with seeded.sessionmaker() as session:
        assert set(await session.scalars(select(Job.status))) == {"succeeded"}
