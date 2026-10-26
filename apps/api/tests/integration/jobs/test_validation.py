import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tenancy import WorkspaceScope
from app.documents.service import StatusConflictError
from app.extractions.models import Extraction
from app.llm.types import TransientLlmError
from app.pipeline.runner import Pipeline, StepContext
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
from app.pipeline.steps.validate import ValidateStep
from app.storage.fake import FakeStorage
from app.validation.models import ValidationIssue
from app.worker.loop import Worker
from tests.support.clock import FrozenClock
from tests.support.documents import PDF
from tests.support.llm import answers, fake_gateway
from tests.support.pipeline import (
    Recorder,
    Seeded,
    document_row,
    events_for,
    llm_calls_for,
    seed_document,
    seed_workspaces,
)
from tests.support.samples import clean_invoice, envelope

CLASSIFIED = {"doc_type": "invoice", "confidence": 0.95}
TODAY = FrozenClock(datetime(2026, 10, 26, tzinfo=UTC))


def misread_total() -> dict[str, Any]:
    data = clean_invoice()
    data["total"]["amount"] = 18826.8  # printed 16826.80; a 6 read as an 8
    return data


def build(seeded: Seeded, storage: FakeStorage, *replies: Any) -> tuple[Worker, Any, ValidateStep]:
    gateway, provider = fake_gateway(seeded.sessionmaker, answers(*replies))
    validate = ValidateStep(gateway, prompt_version="validate/v1", clock=TODAY)
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=Recorder().publish,
        classify=ClassifyStep(gateway, prompt_version="classify/v1"),
        extract=ExtractStep(gateway, prompt_version="extract/v1"),
        validate=validate,
    )
    worker = Worker(
        sessionmaker=seeded.sessionmaker, pipeline=pipeline, events=Recorder(), worker_id="t"
    )
    return worker, provider, validate


async def process(
    seeded: Seeded, storage: FakeStorage, *replies: Any, data: bytes = PDF
) -> uuid.UUID:
    document_id = await seed_document(seeded, storage, data)
    worker, _, _ = build(seeded, storage, *replies)
    await worker.drain()
    return document_id


async def versions(seeded: Seeded, document_id: uuid.UUID) -> list[Extraction]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(Extraction)
            .where(Extraction.document_id == document_id)
            .order_by(Extraction.version)
        )
        return list(rows)


async def issues(seeded: Seeded, document_id: uuid.UUID) -> list[ValidationIssue]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(ValidationIssue)
            .where(ValidationIssue.document_id == document_id)
            .order_by(ValidationIssue.check_name)
        )
        return list(rows)


async def test_ac1_ac6_clean_confident_document_is_approved_by_the_agent(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()

    document_id = await process(
        seeded, storage, CLASSIFIED, envelope(clean_invoice(), total__amount=0.97)
    )

    document = await document_row(seeded, document_id)
    assert (document.status, document.approved_by_agent) == ("APPROVED", True)
    assert document.approved_at is not None
    assert document.approved_by_user_id is None
    assert (await events_for(seeded, document_id))[-2:] == [
        ("EXTRACTING", "VALIDATING"),
        ("VALIDATING", "APPROVED"),
    ]
    # Only the first-time vendor note, which doesn't block approval; no reread was needed.
    assert [(i.check_name, i.severity) for i in await issues(seeded, document_id)] == [
        ("known_vendor", "info")
    ]
    assert [call.task for call in await llm_calls_for(seeded, document_id)] == [
        "classify",
        "extract",
    ]


async def test_ac6_low_confidence_goes_to_review(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()

    document_id = await process(
        seeded, storage, CLASSIFIED, envelope(clean_invoice(), vendor__gstin=0.7)
    )

    document = await document_row(seeded, document_id)
    assert (document.status, document.approved_at) == ("NEEDS_REVIEW", None)


async def test_ac3_ac8_misread_total_fixed_as_agent_version(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    fix = {"path": "total.amount", "value": 16826.80, "confidence": 0.96, "reason": "8 was a 6"}

    document_id = await process(
        seeded,
        storage,
        CLASSIFIED,
        envelope(misread_total(), total__amount=0.93),
        {"fixes": [fix]},
    )

    model, agent = await versions(seeded, document_id)
    assert (model.source, agent.source) == ("model", "agent_fix")
    assert agent.prompt_version == "validate/v1"
    assert agent.data["total"]["amount"] == 16826.8
    assert agent.confidence == {"total.amount": 0.96}
    document = await document_row(seeded, document_id)
    assert (document.current_extraction_id, document.total_amount) == (
        agent.id,
        Decimal("16826.80"),
    )
    assert document.status == "APPROVED"
    stored = {
        (i.check_name, i.fixed_by_agent, i.extraction_id) for i in await issues(seeded, document_id)
    }
    assert stored == {("totals", True, agent.id), ("known_vendor", False, agent.id)}
    calls = await llm_calls_for(seeded, document_id)
    assert [call.task for call in calls] == ["classify", "extract", "validate"]
    assert agent.llm_call_id == calls[-1].id


async def test_unfixable_misread_waits_for_a_person(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()

    document_id = await process(
        seeded, storage, CLASSIFIED, envelope(misread_total(), total__amount=0.93), {"fixes": []}
    )

    assert [v.source for v in await versions(seeded, document_id)] == ["model"]
    assert (await document_row(seeded, document_id)).status == "NEEDS_REVIEW"
    open_issues = [i for i in await issues(seeded, document_id) if i.severity == "error"]
    assert [(i.check_name, i.fixed_by_agent) for i in open_issues] == [("totals", False)]


async def test_provider_down_during_reread_goes_to_review(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()

    document_id = await process(
        seeded,
        storage,
        CLASSIFIED,
        envelope(misread_total(), total__amount=0.93),
        TransientLlmError("fake provider is down"),
    )

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason) == ("NEEDS_REVIEW", None)
    assert "totals" in {i.check_name for i in await issues(seeded, document_id)}


async def test_ac7_duplicate_is_never_auto_approved(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    answer = envelope(clean_invoice(), total__amount=0.99)
    first = await process(seeded, storage, CLASSIFIED, answer)

    second = await process(seeded, storage, CLASSIFIED, answer, data=PDF + b"%copy\n")

    assert (await document_row(seeded, first)).status == "APPROVED"
    assert (await document_row(seeded, second)).status == "NEEDS_REVIEW"
    # The vendor is now known (from the first, approved document); the number is repeated.
    assert [(i.check_name, i.severity) for i in await issues(seeded, second)] == [
        ("duplicate", "warning")
    ]


async def test_duplicate_and_vendor_checks_stay_in_the_workspace(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    w = seeded.workspaces
    in_b = Seeded(
        w,
        WorkspaceScope(workspace_id=w.b.id, user_id=w.b_admin.id, role="admin"),
        seeded.sessionmaker,
    )
    answer = envelope(clean_invoice(), total__amount=0.99)
    await process(in_b, storage, CLASSIFIED, answer)

    document_id = await process(seeded, storage, CLASSIFIED, answer, data=PDF + b"%a\n")

    assert (await document_row(seeded, document_id)).status == "APPROVED"
    assert [i.check_name for i in await issues(seeded, document_id)] == ["known_vendor"]


async def test_ac9_validating_again_stores_nothing_twice(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    fix = {"path": "total.amount", "value": 16826.80, "confidence": 0.96, "reason": "8 was a 6"}
    replies = (CLASSIFIED, envelope(misread_total(), total__amount=0.93), {"fixes": [fix]})
    document_id = await process(seeded, storage, *replies)
    before = (len(await versions(seeded, document_id)), len(await issues(seeded, document_id)))
    _, _, validate = build(seeded, storage, {"fixes": [fix]})
    ctx = StepContext(
        scope=seeded.scope,
        document_id=document_id,
        content_type="application/pdf",
        file=PDF,
        job_id=uuid.uuid4(),
        attempt=2,
        sessionmaker=seeded.sessionmaker,
        publish=Recorder().publish,
    )

    # A duplicate run finds the document already moved on: its writes roll back with it.
    with pytest.raises(StatusConflictError):
        await validate(ctx)

    after = (len(await versions(seeded, document_id)), len(await issues(seeded, document_id)))
    assert after == before == (2, 2)
