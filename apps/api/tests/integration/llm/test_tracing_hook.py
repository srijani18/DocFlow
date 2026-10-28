"""F16: every call the gateway stores is also handed to the tracer, with its stored id."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.llm.models import LlmCall
from app.llm.recording import CallRecord, DbCallRecorder
from tests.support.pipeline import seed_workspaces


class FakeTracer:
    def __init__(self, *, broken: bool = False) -> None:
        self.calls: list[tuple[CallRecord, uuid.UUID]] = []
        self.broken = broken

    def record(self, call: CallRecord, *, call_id: uuid.UUID, ended_at: datetime) -> None:
        if self.broken:
            raise RuntimeError("tracer bug")
        self.calls.append((call, call_id))


def record_for(workspace_id: uuid.UUID) -> CallRecord:
    return CallRecord(
        workspace_id=workspace_id,
        document_id=None,
        job_id=None,
        task="embed",
        provider="gemini",
        model="gemini-embedding-001",
        prompt_version="embed/v1",
        attempt=1,
        outcome="ok",
        error_type=None,
        input_tokens=10,
        output_tokens=None,
        cost_usd=Decimal("0"),
        latency_ms=120,
        route_position=0,
        fallback=False,
        input_mode=None,
    )


async def test_ac4_stored_call_is_traced_with_its_id(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    tracer = FakeTracer()
    call = record_for(seeded.scope.workspace_id)

    call_id = await DbCallRecorder(seeded.sessionmaker, tracer=tracer).record(call)

    assert tracer.calls == [(call, call_id)]


async def test_ac6_a_broken_tracer_never_fails_the_call(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)

    call_id = await DbCallRecorder(seeded.sessionmaker, tracer=FakeTracer(broken=True)).record(
        record_for(seeded.scope.workspace_id)
    )

    async with seeded.sessionmaker() as session:
        stored = await session.scalar(select(LlmCall).where(LlmCall.id == call_id))
    assert stored is not None
