"""AI call traces in Langfuse (F16 AC4-AC6).

Every attempt the gateway records (`CallRecord`, F10) also becomes a Langfuse generation, in
one trace per job (a document's processing run or its search indexing) or per search query.
Only metadata is sent: ids, task, model, prompt version, tokens, cost, latency and outcome.
Never prompts, files, extracted data or query text (AC5): they are customers' documents,
processed with customers' own keys (ADR-0008).

Events go out in batches from a background task, through the SDK's ingestion API, which
takes each call's real start and end time. If Langfuse is slow or down, events are dropped
with a warning; processing never waits for them (AC6).
"""

import asyncio
import contextlib
import uuid
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
import structlog
from langfuse.api import (
    AsyncLangfuseAPI,
    CreateGenerationBody,
    IngestionEvent_GenerationCreate,
    IngestionEvent_TraceCreate,
    IngestionResponse,
    ObservationLevel,
    TraceBody,
)

from app.core.config import Settings
from app.llm.recording import CallRecord

IngestionEvent = IngestionEvent_TraceCreate | IngestionEvent_GenerationCreate

FAILED_OUTCOMES = frozenset({"error", "invalid_output"})
SEND_TIMEOUT_SECONDS = 10
MAX_REMEMBERED_TRACES = 10_000

log = structlog.get_logger(__name__)


class Ingestion(Protocol):
    async def batch(self, *, batch: list[IngestionEvent]) -> IngestionResponse: ...


def trace_id(call: CallRecord, call_id: uuid.UUID) -> str:
    return (call.job_id or call_id).hex


def trace_event(
    call: CallRecord,
    call_id: uuid.UUID,
    *,
    started_at: datetime,
    release: str | None,
    environment: str,
) -> IngestionEvent_TraceCreate:
    return IngestionEvent_TraceCreate(
        type="trace-create",
        id=str(uuid.uuid4()),
        timestamp=started_at.isoformat(),
        body=TraceBody(
            id=trace_id(call, call_id),
            timestamp=started_at,
            name="search query" if call.document_id is None else "document",
            # A document's runs (processing, retries, re-indexing) group into one session.
            session_id=str(call.document_id) if call.document_id else None,
            metadata=_ids(call),
            release=release,
            environment=environment,
        ),
    )


def generation_event(
    call: CallRecord, call_id: uuid.UUID, *, ended_at: datetime, environment: str
) -> IngestionEvent_GenerationCreate:
    usage = {
        name: tokens
        for name, tokens in (("input", call.input_tokens), ("output", call.output_tokens))
        if tokens is not None
    }
    return IngestionEvent_GenerationCreate(
        type="generation-create",
        id=str(uuid.uuid4()),
        timestamp=ended_at.isoformat(),
        body=CreateGenerationBody(
            id=str(call_id),
            trace_id=trace_id(call, call_id),
            name=call.task,
            start_time=ended_at - timedelta(milliseconds=call.latency_ms),
            end_time=ended_at,
            model=call.model,
            version=call.prompt_version,
            level=ObservationLevel("ERROR" if call.outcome in FAILED_OUTCOMES else "DEFAULT"),
            status_message=call.error_type,
            usage_details=usage or None,
            cost_details={"total": float(call.cost_usd)} if call.cost_usd is not None else None,
            metadata={
                **_ids(call),
                "provider": call.provider,
                "outcome": call.outcome,
                "attempt": call.attempt,
                "route_position": call.route_position,
                "fallback": call.fallback,
                "input_mode": call.input_mode,
            },
            environment=environment,
        ),
    )


def _ids(call: CallRecord) -> dict[str, Any]:
    return {
        "workspace_id": str(call.workspace_id),
        "document_id": str(call.document_id) if call.document_id else None,
        "job_id": str(call.job_id) if call.job_id else None,
    }


class LangfuseTracer:
    def __init__(
        self,
        ingestion: Ingestion,
        *,
        environment: str,
        release: str | None,
        flush_seconds: float = 5,
        batch_size: int = 50,
        max_pending: int = 1000,
    ) -> None:
        self._ingestion = ingestion
        self._environment = environment
        self._release = release
        self._flush_seconds = flush_seconds
        self._batch_size = batch_size
        self._max_pending = max_pending
        self._pending: list[IngestionEvent] = []
        self._traces: set[str] = set()  # traces already created by this process
        self._flusher: asyncio.Task[None] | None = None
        self._sends: set[asyncio.Task[None]] = set()
        self.dropped = 0

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient) -> "LangfuseTracer | None":
        """None unless both keys are set (AC8)."""
        if not (settings.langfuse_public_key and settings.langfuse_secret_key):
            return None
        client = AsyncLangfuseAPI(
            base_url=settings.langfuse_host,
            username=settings.langfuse_public_key,
            password=settings.langfuse_secret_key,
            x_langfuse_public_key=settings.langfuse_public_key,
            timeout=SEND_TIMEOUT_SECONDS,
            httpx_client=http,
        )
        log.info("langfuse_enabled", host=settings.langfuse_host)
        return cls(
            client.ingestion,
            environment=settings.sentry_environment or settings.environment,
            release=settings.render_git_commit,
        )

    def record(self, call: CallRecord, *, call_id: uuid.UUID, ended_at: datetime) -> None:
        if len(self._pending) >= self._max_pending:
            self.dropped += 1
            return
        trace = trace_id(call, call_id)
        if trace not in self._traces:
            if len(self._traces) >= MAX_REMEMBERED_TRACES:
                self._traces.clear()
            self._traces.add(trace)
            started_at = ended_at - timedelta(milliseconds=call.latency_ms)
            self._pending.append(
                trace_event(
                    call,
                    call_id,
                    started_at=started_at,
                    release=self._release,
                    environment=self._environment,
                )
            )
        self._pending.append(
            generation_event(call, call_id, ended_at=ended_at, environment=self._environment)
        )
        if self._flusher is None:
            self._flusher = asyncio.create_task(self._flush_periodically(), name="langfuse")
        if len(self._pending) >= self._batch_size:
            self._send_in_background()

    async def flush(self) -> None:
        batch, self._pending = self._pending, []
        if not batch:
            return
        try:
            response = await self._ingestion.batch(batch=batch)
        except Exception as exc:  # never let tracing fail anything (AC6)
            self.dropped += len(batch)
            log.warning("langfuse_send_failed", events=len(batch), error_type=type(exc).__name__)
            return
        if response.errors:
            self.dropped += len(response.errors)
            log.warning("langfuse_events_rejected", events=len(response.errors))

    async def aclose(self) -> None:
        if self._flusher is not None:
            self._flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flusher
            self._flusher = None
        await asyncio.gather(*self._sends, return_exceptions=True)
        await self.flush()
        if self.dropped:
            log.warning("langfuse_events_dropped", events=self.dropped)

    def _send_in_background(self) -> None:
        task = asyncio.create_task(self.flush())
        self._sends.add(task)
        task.add_done_callback(self._sends.discard)

    async def _flush_periodically(self) -> None:
        while True:
            await asyncio.sleep(self._flush_seconds)
            await self.flush()
