import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.llm.models import LlmCall
from app.llm.prompts import load_prompt
from app.llm.types import (
    CallContext,
    InvalidOutputError,
    LlmRequest,
    ProviderResponse,
    TextPart,
    TransientLlmError,
)
from app.schemas_registry import bundle
from tests.support.llm import fake_gateway
from tests.support.pipeline import Seeded, seed_workspaces

SCHEMA = "docflow/classification/v1"


def request(seeded: Seeded, attempt: int = 1) -> LlmRequest:
    return LlmRequest(
        task="classify",
        prompt=load_prompt("classify/v1"),
        parts=[TextPart("hello")],
        response_schema=bundle(SCHEMA),
        context=CallContext(
            workspace_id=seeded.scope.workspace_id, document_id=None, job_id=None, attempt=attempt
        ),
    )


async def calls(seeded: Seeded) -> list[LlmCall]:
    async with seeded.sessionmaker() as session:
        return list(await session.scalars(select(LlmCall).order_by(LlmCall.created_at)))


async def test_ac4_every_attempt_logged_with_tokens_cost_latency(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    gateway, provider = fake_gateway(
        seeded.sessionmaker, lambda _r: {"doc_type": "invoice", "confidence": 0.93}
    )

    result = await gateway.generate(request(seeded, attempt=2), validate_with=SCHEMA)

    assert result.data == {"doc_type": "invoice", "confidence": Decimal("0.93")}
    assert result.prompt_version == "classify/v1"
    [call] = await calls(seeded)
    assert call.id == result.call_id
    assert (call.task, call.provider, call.model, call.prompt_version) == (
        "classify",
        "fake",
        "fake-model",
        "classify/v1",
    )
    assert (call.outcome, call.attempt, call.input_tokens, call.output_tokens) == (
        "ok",
        2,
        1000,
        50,
    )
    assert call.cost_usd == Decimal("0.001100")  # 1000 at $1/M plus 50 at $2/M
    assert call.latency_ms >= 0
    assert provider.requests[0].response_schema == bundle(SCHEMA)


@pytest.mark.parametrize(
    "answer",
    [
        {"doc_type": "letter", "confidence": 0.5},
        {"doc_type": "invoice"},
        "not json",
        "[1, 2]",
        ProviderResponse(
            text='{"doc_type": "inv',
            model="fake-model",
            input_tokens=1,
            output_tokens=1,
            truncated=True,
        ),
    ],
)
async def test_ac2_invalid_output_raises_and_is_logged(
    committing_engine: AsyncEngine, answer: object
) -> None:
    seeded = await seed_workspaces(committing_engine)
    gateway, _ = fake_gateway(seeded.sessionmaker, lambda _r: answer)  # type: ignore[arg-type,return-value]

    with pytest.raises(InvalidOutputError):
        await gateway.generate(request(seeded), validate_with=SCHEMA)

    [call] = await calls(seeded)
    assert (call.outcome, call.error_type) == ("invalid_output", "InvalidOutputError")


async def test_provider_errors_are_logged_and_raised(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gateway, _ = fake_gateway(
        seeded.sessionmaker, lambda _r: TransientLlmError("429", retry_after_seconds=30)
    )

    with pytest.raises(TransientLlmError):
        await gateway.generate(request(seeded), validate_with=SCHEMA)

    [call] = await calls(seeded)
    assert (call.outcome, call.error_type, call.input_tokens, call.cost_usd) == (
        "error",
        "TransientLlmError",
        None,
        None,
    )
    assert isinstance(call.id, uuid.UUID)
