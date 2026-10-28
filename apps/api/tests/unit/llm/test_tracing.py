import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from langfuse.api import (
    IngestionEvent_GenerationCreate,
    IngestionEvent_TraceCreate,
    IngestionResponse,
)

from app.llm.recording import CallRecord
from app.llm.tracing import IngestionEvent, LangfuseTracer
from tests.conftest import make_settings

ENDED = datetime(2026, 1, 10, 12, 0, 5, tzinfo=UTC)
WORKSPACE = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT = uuid.UUID("22222222-2222-2222-2222-222222222222")
JOB = uuid.UUID("33333333-3333-3333-3333-333333333333")

# Every field the event may carry (AC4, AC5); anything else is a leak.
ALLOWED_GENERATION_FIELDS = {
    "id",
    "trace_id",
    "name",
    "start_time",
    "end_time",
    "model",
    "version",
    "level",
    "status_message",
    "usage_details",
    "cost_details",
    "metadata",
    "environment",
}
ALLOWED_TRACE_FIELDS = {
    "id",
    "timestamp",
    "name",
    "session_id",
    "metadata",
    "release",
    "environment",
}


def call(**overrides: object) -> CallRecord:
    values: dict[str, object] = {
        "workspace_id": WORKSPACE,
        "document_id": DOCUMENT,
        "job_id": JOB,
        "task": "extract",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "prompt_version": "extract/v1",
        "attempt": 1,
        "outcome": "ok",
        "error_type": None,
        "input_tokens": 1200,
        "output_tokens": 300,
        "cost_usd": Decimal("0.000450"),
        "latency_ms": 2500,
        "route_position": 0,
        "fallback": False,
        "input_mode": "inline",
    }
    return CallRecord(**(values | overrides))  # type: ignore[arg-type]


class FakeIngestion:
    def __init__(self, *, fail: bool = False, delay: float = 0) -> None:
        self.batches: list[list[IngestionEvent]] = []
        self.fail = fail
        self.delay = delay

    async def batch(self, *, batch: list[IngestionEvent]) -> IngestionResponse:
        await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("langfuse unreachable")
        self.batches.append(batch)
        return IngestionResponse(successes=[], errors=[])

    @property
    def events(self) -> list[IngestionEvent]:
        return [event for batch in self.batches for event in batch]


def tracer(ingestion: FakeIngestion, **options: float) -> LangfuseTracer:
    return LangfuseTracer(ingestion, environment="production", release="abc123", **options)  # type: ignore[arg-type]


async def test_ac4_ac5_one_trace_per_job_with_metadata_only() -> None:
    ingestion = FakeIngestion()
    traces = tracer(ingestion)
    first, second = uuid.uuid4(), uuid.uuid4()

    traces.record(call(task="classify"), call_id=first, ended_at=ENDED)
    traces.record(
        call(outcome="error", error_type="TransientLlmError", cost_usd=None, input_tokens=None),
        call_id=second,
        ended_at=ENDED,
    )
    await traces.aclose()

    trace, classify, extract = ingestion.events
    assert isinstance(trace, IngestionEvent_TraceCreate)
    assert isinstance(classify, IngestionEvent_GenerationCreate)
    assert isinstance(extract, IngestionEvent_GenerationCreate)
    assert set(trace.body.model_dump(exclude_none=True)) <= ALLOWED_TRACE_FIELDS
    assert trace.body.id == JOB.hex
    assert trace.body.session_id == str(DOCUMENT)
    assert trace.body.release == "abc123"
    for generation in (classify, extract):
        assert set(generation.body.model_dump(exclude_none=True)) <= ALLOWED_GENERATION_FIELDS
        assert generation.body.trace_id == JOB.hex
    assert classify.body.id == str(first)
    assert classify.body.end_time == ENDED
    assert classify.body.start_time is not None
    assert (ENDED - classify.body.start_time).total_seconds() == 2.5
    assert classify.body.usage_details == {"input": 1200, "output": 300}
    assert classify.body.cost_details == {"total": 0.00045}
    assert (classify.body.metadata or {})["outcome"] == "ok"
    assert classify.body.level == "DEFAULT"
    assert (extract.body.level, extract.body.status_message) == ("ERROR", "TransientLlmError")
    assert extract.body.usage_details == {"output": 300}
    assert extract.body.cost_details is None


async def test_ac4_search_query_is_its_own_trace() -> None:
    ingestion = FakeIngestion()
    traces = tracer(ingestion)
    call_id = uuid.uuid4()

    traces.record(
        call(task="embed", document_id=None, job_id=None), call_id=call_id, ended_at=ENDED
    )
    await traces.aclose()

    trace, generation = ingestion.events
    assert isinstance(trace, IngestionEvent_TraceCreate)
    assert isinstance(generation, IngestionEvent_GenerationCreate)
    assert (trace.body.id, trace.body.name, trace.body.session_id) == (
        call_id.hex,
        "search query",
        None,
    )
    assert generation.body.trace_id == call_id.hex


async def test_ac5_no_inputs_or_outputs_are_sent() -> None:
    ingestion = FakeIngestion()
    traces = tracer(ingestion)

    traces.record(call(), call_id=uuid.uuid4(), ended_at=ENDED)
    await traces.aclose()

    for event in ingestion.events:
        body = event.body.model_dump()
        assert body.get("input") is None
        assert body.get("output") is None


async def test_ac6_unreachable_langfuse_drops_events_without_raising() -> None:
    ingestion = FakeIngestion(fail=True)
    traces = tracer(ingestion, batch_size=2)

    for _ in range(3):
        traces.record(call(), call_id=uuid.uuid4(), ended_at=ENDED)
    await traces.aclose()

    assert ingestion.events == []
    assert traces.dropped == 4  # one trace and three generations


async def test_ac6_recording_never_waits_for_sending() -> None:
    ingestion = FakeIngestion(delay=5)
    traces = tracer(ingestion, batch_size=1)
    loop = asyncio.get_running_loop()

    started = loop.time()
    for _ in range(20):
        traces.record(call(), call_id=uuid.uuid4(), ended_at=ENDED)
    elapsed = loop.time() - started

    assert elapsed < 0.05
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()


async def test_ac6_pending_events_are_capped() -> None:
    ingestion = FakeIngestion()
    traces = tracer(ingestion, max_pending=3, batch_size=100)

    for _ in range(5):
        traces.record(call(), call_id=uuid.uuid4(), ended_at=ENDED)
    await traces.aclose()

    assert len(ingestion.events) == 3
    assert traces.dropped == 3


@pytest.mark.parametrize(
    ("public_key", "secret_key"), [(None, None), ("pk-lf-1", None), (None, "sk-lf-1")]
)
def test_ac8_off_without_both_keys(public_key: str | None, secret_key: str | None) -> None:
    settings = make_settings(langfuse_public_key=public_key, langfuse_secret_key=secret_key)

    assert LangfuseTracer.from_settings(settings, http=None) is None  # type: ignore[arg-type]
