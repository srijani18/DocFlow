import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.llm.circuit import CircuitBreaker
from app.llm.gateway import Gateway
from app.llm.inputs import Capabilities
from app.llm.models import LlmCall
from app.llm.prompts import load_prompt
from app.llm.providers.fake import FakeProvider
from app.llm.routing import RouteEntry
from app.llm.types import (
    CallContext,
    FilePart,
    InvalidOutputError,
    LlmRequest,
    NoCredentialsError,
    PermanentLlmError,
    TextPart,
    TransientLlmError,
)
from app.schemas_registry import bundle
from tests.support.llm import StaticCredentials
from tests.support.pipeline import Seeded, seed_workspaces

SCHEMA = "docflow/classification/v1"
GOOD = {"doc_type": "invoice", "confidence": 0.9}
PDF = (
    Path(__file__).resolve().parents[5] / "evals" / "samples" / "synthetic-invoice-001.pdf"
).read_bytes()


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def provider(name: str, *answers: Any, reads_pdf: bool = True) -> FakeProvider:
    remaining = list(answers)
    return FakeProvider(
        lambda _r: remaining.pop(0) if len(remaining) > 1 else remaining[0],
        name=name,
        capabilities=Capabilities(reads_pdf=reads_pdf, max_images=5),
    )


def gateway(
    seeded: Seeded,
    *providers: FakeProvider,
    keys: set[str] | None = None,
    breaker: CircuitBreaker | None = None,
    ttl: timedelta = timedelta(days=30),
) -> Gateway:
    names = [p.name for p in providers]
    return Gateway(
        sessionmaker=seeded.sessionmaker,
        providers={p.name: p for p in providers},
        routes={"classify": tuple(RouteEntry(n, f"{n}-model") for n in names)},
        credentials=StaticCredentials(keys={n: f"{n}-key" for n in (keys or set(names))}),
        breaker=breaker,
        cache_ttl=ttl,
    )


def request(
    seeded: Seeded,
    *,
    file: bytes = b"%PDF-1",
    workspace: uuid.UUID | None = None,
    use_cache: bool = True,
) -> LlmRequest:
    return LlmRequest(
        task="classify",
        prompt=load_prompt("classify/v1"),
        parts=[TextPart("hi"), FilePart("application/pdf", file)],
        response_schema=bundle(SCHEMA),
        context=CallContext(
            workspace_id=workspace or seeded.scope.workspace_id,
            document_id=None,
            job_id=None,
            attempt=1,
        ),
        use_cache=use_cache,
    )


async def calls(seeded: Seeded) -> list[tuple[str, str, int, bool]]:
    async with seeded.sessionmaker() as session:
        rows = await session.scalars(
            select(LlmCall).order_by(LlmCall.created_at, LlmCall.route_position)
        )
        return [(c.provider, c.outcome, c.route_position, c.fallback) for c in rows]


async def test_ac1_first_success_stops(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    first, second = provider("gemini", GOOD), provider("groq", GOOD)

    result = await gateway(seeded, first, second).generate(request(seeded), validate_with=SCHEMA)

    assert result.data["doc_type"] == "invoice"
    assert (len(first.requests), len(second.requests)) == (1, 0)
    assert first.requests[0].api_key == "gemini-key"
    assert await calls(seeded) == [("gemini", "ok", 0, False)]


async def test_ac2_transient_and_invalid_fall_through(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    providers = (
        provider("gemini", TransientLlmError("503")),
        provider("groq", {"doc_type": "letter", "confidence": 2}),
        provider("openrouter", GOOD),
    )

    result = await gateway(seeded, *providers).generate(request(seeded), validate_with=SCHEMA)

    assert result.data["doc_type"] == "invoice"
    assert await calls(seeded) == [
        ("gemini", "error", 0, False),
        ("groq", "invalid_output", 1, True),
        ("openrouter", "ok", 2, True),
    ]


async def test_ac2_everything_temporary_raises_transient_with_longest_wait(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    providers = (
        provider("gemini", TransientLlmError("429", retry_after_seconds=10)),
        provider("groq", TransientLlmError("429", retry_after_seconds=40)),
    )

    with pytest.raises(TransientLlmError) as raised:
        await gateway(seeded, *providers).generate(request(seeded), validate_with=SCHEMA)

    assert raised.value.retry_after_seconds == 40


async def test_ac3_permanent_falls_through_then_permanent_if_all(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    recovered = await gateway(
        seeded, provider("gemini", PermanentLlmError("unreadable")), provider("groq", GOOD)
    ).generate(request(seeded), validate_with=SCHEMA)
    assert recovered.data["doc_type"] == "invoice"

    with pytest.raises(PermanentLlmError):
        await gateway(
            seeded,
            provider("gemini", PermanentLlmError("x")),
            provider("groq", PermanentLlmError("y")),
        ).generate(request(seeded, file=b"%PDF-2"), validate_with=SCHEMA)


async def test_invalid_everywhere_is_invalid_output(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)

    with pytest.raises(InvalidOutputError):
        await gateway(seeded, provider("gemini", "nope"), provider("groq", "[]")).generate(
            request(seeded), validate_with=SCHEMA
        )


async def test_ac4_open_circuit_skips_and_logs(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    clock = Clock()
    breaker = CircuitBreaker(clock=clock)
    flaky, backup = provider("gemini", TransientLlmError("503")), provider("groq", GOOD)
    gw = gateway(seeded, flaky, backup, breaker=breaker)

    for n in range(4):
        await gw.generate(request(seeded, file=f"%PDF-{n}".encode()), validate_with=SCHEMA)

    assert len(flaky.requests) == 3  # the 4th request skipped it
    assert (await calls(seeded))[-2:] == [("gemini", "skipped", 0, False), ("groq", "ok", 1, True)]

    clock.now = 61  # rested: one trial request goes through again
    await gw.generate(request(seeded, file=b"%PDF-9"), validate_with=SCHEMA)
    assert len(flaky.requests) == 4


async def test_ac5_pdf_sent_as_images_to_image_only_provider(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    image_only = provider("groq", GOOD, reads_pdf=False)

    await gateway(seeded, image_only).generate(request(seeded, file=PDF), validate_with=SCHEMA)

    sent = image_only.requests[0].parts
    assert isinstance(sent[0], TextPart)
    assert [p.mime_type for p in sent[1:]] == ["image/png"] * (len(sent) - 1)  # type: ignore[union-attr]
    async with seeded.sessionmaker() as session:
        assert await session.scalar(select(LlmCall.input_mode)) == "images"


async def test_ac9_unconnected_providers_skipped(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gemini, groq = provider("gemini", GOOD), provider("groq", GOOD)

    await gateway(seeded, gemini, groq, keys={"groq"}).generate(
        request(seeded), validate_with=SCHEMA
    )

    assert (len(gemini.requests), len(groq.requests)) == (0, 1)
    assert await calls(seeded) == [("groq", "ok", 1, True)]
    with pytest.raises(NoCredentialsError):
        await gateway(seeded, gemini, keys={"nothing"}).generate(
            request(seeded), validate_with=SCHEMA
        )


async def test_ac6_identical_request_hits_cache_without_provider_call(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    gemini = provider("gemini", GOOD)
    gw = gateway(seeded, gemini)

    first = await gw.generate(request(seeded), validate_with=SCHEMA)
    second = await gw.generate(request(seeded), validate_with=SCHEMA)
    different_file = await gw.generate(request(seeded, file=b"%PDF-other"), validate_with=SCHEMA)

    assert second.data == first.data
    assert len(gemini.requests) == 2  # the first and the different file
    async with seeded.sessionmaker() as session:
        rows = list(await session.scalars(select(LlmCall).order_by(LlmCall.created_at)))
    assert [r.outcome for r in rows] == ["ok", "cache_hit", "ok"]
    assert rows[1].cost_usd == 0
    assert different_file.call_id == rows[2].id


async def test_ac6_cache_never_crosses_workspaces(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gemini = provider("gemini", GOOD)
    gw = gateway(seeded, gemini)

    await gw.generate(request(seeded), validate_with=SCHEMA)
    await gw.generate(request(seeded, workspace=seeded.workspaces.b.id), validate_with=SCHEMA)

    assert len(gemini.requests) == 2


async def test_ac6_failures_not_cached_and_cache_can_be_bypassed(
    committing_engine: AsyncEngine,
) -> None:
    seeded = await seed_workspaces(committing_engine)
    gemini = provider("gemini", TransientLlmError("503"), GOOD)
    gw = gateway(seeded, gemini)

    with pytest.raises(TransientLlmError):
        await gw.generate(request(seeded), validate_with=SCHEMA)
    await gw.generate(request(seeded), validate_with=SCHEMA)
    await gw.generate(request(seeded, use_cache=False), validate_with=SCHEMA)

    assert len(gemini.requests) == 3


async def test_ac6_expired_entries_ignored(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gemini = provider("gemini", GOOD)
    gw = gateway(seeded, gemini, ttl=timedelta(seconds=0))

    await gw.generate(request(seeded), validate_with=SCHEMA)
    await gw.generate(request(seeded), validate_with=SCHEMA)

    assert len(gemini.requests) == 2
