"""Where the gateway writes its call log (constitution §5.2).

The app uses the `llm_calls` table. Evals keep calls in memory, so they need no database
and create nothing in product data (F11 AC8).
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.models import LlmCall


@dataclass(frozen=True)
class CallRecord:
    workspace_id: uuid.UUID
    document_id: uuid.UUID | None
    job_id: uuid.UUID | None
    task: str
    provider: str
    model: str
    prompt_version: str
    attempt: int
    outcome: str
    error_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None
    latency_ms: int
    route_position: int
    fallback: bool
    input_mode: str | None


class CallRecorder(Protocol):
    async def record(self, call: CallRecord) -> uuid.UUID: ...


class DbCallRecorder:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def record(self, call: CallRecord) -> uuid.UUID:
        # Its own short transaction: a failed attempt is kept even when the step rolls back.
        async with self._sessionmaker() as session, session.begin():
            call_id: uuid.UUID = (
                await session.execute(insert(LlmCall).values(**call.__dict__).returning(LlmCall.id))
            ).scalar_one()
        return call_id


@dataclass
class MemoryCallRecorder:
    calls: list[CallRecord] = field(default_factory=list)

    async def record(self, call: CallRecord) -> uuid.UUID:
        self.calls.append(call)
        return uuid.uuid4()
