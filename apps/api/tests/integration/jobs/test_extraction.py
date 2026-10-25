import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents.models import Document
from app.extractions.models import Extraction
from app.jobs.models import Job
from app.pipeline.runner import Pipeline
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
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
from tests.support.samples import envelope, purchase_order_data, sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
RECEIPT = sample_truth("synthetic-receipt-001")["data"]


def classified(doc_type: str) -> dict[str, Any]:
    return {"doc_type": doc_type, "confidence": 0.95}


def full_worker(seeded: Seeded, storage: FakeStorage, *replies: Any) -> tuple[Worker, Any]:
    gateway, provider = fake_gateway(seeded.sessionmaker, answers(*replies))
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=Recorder().publish,
        classify=ClassifyStep(gateway, prompt_version="classify/v1"),
        extract=ExtractStep(gateway, prompt_version="extract/v1"),
    )
    return Worker(
        sessionmaker=seeded.sessionmaker, pipeline=pipeline, events=Recorder(), worker_id="t"
    ), provider


async def extractions_for(seeded: Seeded, document_id: Any) -> list[Extraction]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(Extraction)
            .where(Extraction.document_id == document_id)
            .order_by(Extraction.version)
        )
        return list(rows)


@pytest.mark.parametrize(
    ("doc_type", "data", "schema_id"),
    [
        ("invoice", INVOICE, "docflow/invoice/v1"),
        ("receipt", RECEIPT, "docflow/receipt/v1"),
        ("purchase_order", purchase_order_data(), "docflow/purchase_order/v1"),
    ],
)
async def test_ac1_invoice_receipt_po_extracted_to_needs_review(
    committing_engine: AsyncEngine, doc_type: str, data: dict[str, Any], schema_id: str
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, provider = full_worker(
        seeded, storage, classified(doc_type), envelope(data, total__amount=0.97)
    )

    await worker.drain()

    document = await document_row(seeded, document_id)
    [extraction] = await extractions_for(seeded, document_id)
    assert document.status == "NEEDS_REVIEW"
    assert document.current_extraction_id == extraction.id
    assert (extraction.version, extraction.schema_id) == (1, schema_id)
    assert extraction.data["total"] == data["total"]
    assert extraction.confidence == {"total.amount": 0.97}
    extract_request = provider.requests[1]
    assert extract_request.parts[0].text == f"Document type: {doc_type}"
    assert extract_request.response_schema["properties"]["data"]["title"]


async def test_ac4_extraction_records_provenance(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = full_worker(seeded, storage, classified("invoice"), envelope(INVOICE))

    await worker.drain()

    [extraction] = await extractions_for(seeded, document_id)
    calls = await llm_calls_for(seeded, document_id)
    assert [(c.task, c.outcome) for c in calls] == [("classify", "ok"), ("extract", "ok")]
    assert (extraction.source, extraction.prompt_version, extraction.llm_call_id) == (
        "model",
        "extract/v1",
        calls[1].id,
    )


async def test_ac7_summary_columns_per_type(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = full_worker(seeded, storage, classified("receipt"), envelope(RECEIPT))

    await worker.drain()

    document = await document_row(seeded, document_id)
    assert (document.vendor_name, str(document.document_date), document.currency) == (
        "Annapurna Tiffin Centre",
        "2026-09-02",
        "INR",
    )
    assert document.total_amount == Decimal("346.50")


async def test_ac8_amounts_stored_exactly(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    data = json.dumps(INVOICE)
    total = json.dumps({"total": INVOICE["total"]})[1:-1]
    assert total in data
    precise = '"total": {"amount": 123456789012.34567890123, "currency": "INR"}'
    answer = f'{{"data": {data.replace(total, precise)}, "confidence": []}}'
    worker, _ = full_worker(seeded, storage, classified("invoice"), answer)

    await worker.drain()

    async with seeded.sessionmaker() as session:
        stored = await session.scalar(
            text("SELECT data->'total'->>'amount' FROM docflow.extractions WHERE document_id = :d"),
            {"d": document_id},
        )
    assert stored == "123456789012.34567890123"


async def test_ac3_invalid_answer_not_stored_and_retried(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    bad = envelope({**INVOICE, "invoice_date": "14/08/2026"})
    worker, _ = full_worker(seeded, storage, classified("invoice"), bad, envelope(INVOICE))

    await worker.drain()
    assert await extractions_for(seeded, document_id) == []
    [job] = await jobs_for(seeded, document_id)
    assert (job.status, (await document_row(seeded, document_id)).status) == (
        "queued",
        "EXTRACTING",
    )

    await make_due_now(seeded)
    await worker.drain()

    assert len(await extractions_for(seeded, document_id)) == 1
    assert [c.outcome for c in await llm_calls_for(seeded, document_id)] == [
        "ok",
        "invalid_output",
        "ok",
    ]


async def test_ac3_fails_after_last_attempt(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = full_worker(seeded, storage, classified("invoice"), envelope({"nope": 1}))

    for _ in range(5):
        await worker.drain()
        await make_due_now(seeded)

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason) == (
        "FAILED",
        "Couldn't extract valid data after 5 attempts",
    )
    assert await extractions_for(seeded, document_id) == []


async def test_ac5_rerun_no_call_no_new_version(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, provider = full_worker(seeded, storage, classified("invoice"), envelope(INVOICE))
    await worker.drain()
    # As if the worker crashed after committing the extraction but before finishing the job:
    # the document is put back to EXTRACTING and the job is queued again.
    async with seeded.sessionmaker() as session, session.begin():
        await session.execute(update(Document).values(status="EXTRACTING"))
        await session.execute(update(Job).values(status="queued", run_after=Job.created_at))

    await worker.drain()

    assert len(provider.requests) == 2  # classify + extract, nothing more
    assert len(await extractions_for(seeded, document_id)) == 1
    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"


async def test_retry_after_failure_adds_a_new_version(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    worker, _ = full_worker(seeded, storage, classified("invoice"), envelope(INVOICE))
    await worker.drain()
    async with seeded.sessionmaker() as session, session.begin():
        # A later run (retry) has a new processing generation and stores version 2.
        await session.execute(update(Document).values(status="EXTRACTING", processing_generation=2))
        await session.execute(update(Job).values(status="queued", run_after=Job.created_at))

    await worker.drain()

    versions = await extractions_for(seeded, document_id)
    assert [(e.version, e.processing_generation) for e in versions] == [(1, 1), (2, 2)]
    assert (await document_row(seeded, document_id)).current_extraction_id == versions[1].id
