from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents.models import DocumentEvent
from app.jobs.models import Job
from app.llm.types import InvalidOutputError, TransientLlmError
from app.pipeline.runner import Pipeline, StepContext, skip_extraction
from app.pipeline.steps.classify import ClassifyStep
from app.storage.fake import FakeStorage
from app.worker.loop import Worker
from tests.support.llm import answers, fake_gateway
from tests.support.pipeline import (
    Recorder,
    Seeded,
    document_row,
    jobs_for,
    llm_calls_for,
    make_due_now,
    seed_document,
    seed_workspaces,
)

INVOICE = {"doc_type": "invoice", "confidence": 0.91}


def classifying_worker(
    seeded: Seeded, storage: FakeStorage, *replies: Any, extract: Any = skip_extraction
) -> tuple[Worker, Any]:
    gateway, provider = fake_gateway(seeded.sessionmaker, answers(*replies))
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=Recorder().publish,
        classify=ClassifyStep(gateway, prompt_version="classify/v1"),
        extract=extract,
    )
    worker = Worker(
        sessionmaker=seeded.sessionmaker, pipeline=pipeline, events=Recorder(), worker_id="t"
    )
    return worker, provider


async def test_ac1_label_and_confidence_stored(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, provider = classifying_worker(seeded, storage, INVOICE)

    await worker.drain()

    document = await document_row(seeded, document_id)
    assert (document.doc_type, document.doc_type_confidence, document.status) == (
        "invoice",
        0.91,
        "NEEDS_REVIEW",
    )
    [request] = provider.requests
    assert request.parts[0].mime_type == "application/pdf"
    [call] = await llm_calls_for(seeded, document_id)
    assert (call.task, call.outcome, call.attempt) == ("classify", "ok", 1)


async def test_ac3_other_goes_to_needs_review_with_note(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    extracted = []

    async def extract(ctx: StepContext) -> None:
        extracted.append(ctx.document_id)
        await skip_extraction(ctx)

    worker, _ = classifying_worker(
        seeded, storage, {"doc_type": "other", "confidence": 0.8}, extract=extract
    )
    await worker.drain()

    document = await document_row(seeded, document_id)
    assert (document.status, document.doc_type) == ("NEEDS_REVIEW", "other")
    assert extracted == []
    async with seeded.sessionmaker() as session:
        detail = await session.scalar(
            select(DocumentEvent.detail).where(DocumentEvent.to_status == "NEEDS_REVIEW")
        )
    assert detail == "Not an invoice, receipt or purchase order"


async def test_ac2_invalid_output_logged_and_retried(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = classifying_worker(
        seeded, storage, {"doc_type": "letter", "confidence": 2}, INVOICE
    )

    await worker.drain()
    [job] = await jobs_for(seeded, document_id)
    document = await document_row(seeded, document_id)
    assert (job.status, document.status, document.doc_type) == ("queued", "CLASSIFYING", None)
    assert "invalid output" in (job.last_error or "")

    await make_due_now(seeded)
    await worker.drain()

    assert (await document_row(seeded, document_id)).doc_type == "invoice"
    outcomes = [call.outcome for call in await llm_calls_for(seeded, document_id)]
    assert outcomes == ["invalid_output", "ok"]


async def test_ac5_rate_limit_waits_at_least_retry_after(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = classifying_worker(
        seeded, storage, TransientLlmError("429", retry_after_seconds=600)
    )

    await worker.drain()

    [job] = await jobs_for(seeded, document_id)
    async with seeded.sessionmaker() as session:
        now = await session.scalar(select(Job.updated_at).where(Job.id == job.id))
    assert now is not None
    assert (job.run_after - now).total_seconds() >= 599
    [call] = await llm_calls_for(seeded, document_id)
    assert (call.outcome, call.error_type) == ("error", "TransientLlmError")


async def test_ac7_rerun_makes_no_call(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    extract_calls = 0

    async def extract_failing_once(ctx: StepContext) -> None:
        nonlocal extract_calls
        extract_calls += 1
        if extract_calls == 1:
            raise InvalidOutputError("bad")  # unexpected type → transient
        await skip_extraction(ctx)

    worker, provider = classifying_worker(seeded, storage, INVOICE, extract=extract_failing_once)
    await worker.drain()
    await make_due_now(seeded)
    await worker.drain()

    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    assert len(provider.requests) == 1  # classified once, not again on the re-run
    assert extract_calls == 2
