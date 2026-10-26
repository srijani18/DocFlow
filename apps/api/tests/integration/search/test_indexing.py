import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents.models import Document
from app.jobs.models import Job
from app.pipeline.runner import Pipeline
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
from app.search.backfill import backfill
from app.search.indexer import EmbedRunner
from app.search.models import EMBEDDING_DIMENSIONS, DocumentEmbedding
from app.storage.fake import FakeStorage
from app.worker.loop import Worker
from tests.support.llm import StaticCredentials, answers, fake_gateway
from tests.support.pipeline import (
    Recorder,
    Seeded,
    document_row,
    jobs_for,
    seed_document,
    seed_workspaces,
)
from tests.support.samples import envelope, sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
CLASSIFIED = {"doc_type": "invoice", "confidence": 0.95}


def worker(seeded: Seeded, storage: FakeStorage, credentials: Any = None) -> tuple[Worker, Any]:
    gateway, provider = fake_gateway(
        seeded.sessionmaker, answers(CLASSIFIED, envelope(INVOICE)), credentials
    )
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=Recorder().publish,
        classify=ClassifyStep(gateway, prompt_version="classify/v1"),
        extract=ExtractStep(gateway, prompt_version="extract/v1"),
    )
    return Worker(
        sessionmaker=seeded.sessionmaker,
        pipeline=pipeline,
        events=Recorder(),
        embedder=EmbedRunner(gateway, sessionmaker=seeded.sessionmaker),
        worker_id="t",
    ), provider


async def embedding_of(seeded: Seeded, document_id: uuid.UUID) -> DocumentEmbedding | None:
    async with seeded.sessionmaker() as session:
        row: DocumentEmbedding | None = await session.scalar(
            select(DocumentEmbedding).where(DocumentEmbedding.document_id == document_id)
        )
        return row


async def test_ac6_ac7_extraction_is_embedded_by_a_job(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    run, provider = worker(seeded, storage)

    await run.drain()

    document = await document_row(seeded, document_id)
    embedding = await embedding_of(seeded, document_id)
    assert embedding is not None
    assert embedding.extraction_id == document.current_extraction_id
    assert len(embedding.embedding) == EMBEDDING_DIMENSIONS
    [request] = provider.embed_requests
    assert request.purpose == "document"
    assert "Kaveri Fasteners" in request.texts[0]  # the extracted data, not the file
    [job] = await jobs_for(seeded, document_id, kind="embed_document")
    assert job.status == "succeeded"


async def test_ac5_no_key_leaves_the_document_alone(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    run, provider = worker(seeded, storage)
    await run.drain()
    # A second embedding attempt without a key: the job ends quietly, status untouched.
    no_key, _ = worker(seeded, storage, StaticCredentials(without={seeded.scope.workspace_id}))
    async with seeded.sessionmaker() as session, session.begin():
        await session.execute(
            update(Job).where(Job.kind == "embed_document").values(status="queued", attempts=0)
        )
        await session.execute(
            DocumentEmbedding.__table__.delete()  # type: ignore[attr-defined]
        )

    await no_key.drain()

    assert await embedding_of(seeded, document_id) is None
    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    [job] = await jobs_for(seeded, document_id, kind="embed_document")
    assert job.status == "succeeded"
    assert len(provider.embed_requests) == 1


async def test_ac8_backfill_reindexes_and_queues_missing_embeddings(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    run, _ = worker(seeded, storage)
    await run.drain()
    async with seeded.sessionmaker() as session, session.begin():
        await session.execute(
            update(Document).where(Document.id == document_id).values(search_text="")
        )
        await session.execute(DocumentEmbedding.__table__.delete())  # type: ignore[attr-defined]
        await session.execute(Job.__table__.delete().where(Job.kind == "embed_document"))  # type: ignore[attr-defined]

    async with seeded.sessionmaker() as session, session.begin():
        assert await backfill(session) == (1, 1)
    async with seeded.sessionmaker() as session, session.begin():
        assert await backfill(session) == (1, 0)  # already queued: nothing new
    await run.drain()

    assert "Kaveri" in (await document_row(seeded, document_id)).search_text
    assert await embedding_of(seeded, document_id) is not None
