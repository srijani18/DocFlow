import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.llm.models import LlmCall
from app.llm.types import CallContext, EmbedRequest, NoCredentialsError, TransientLlmError
from tests.support.llm import StaticCredentials, fake_gateway
from tests.support.pipeline import Seeded, seed_workspaces


def embed_request(seeded: Seeded, *texts: str, purpose: str = "query") -> EmbedRequest:
    return EmbedRequest(
        texts=list(texts),
        purpose=purpose,  # type: ignore[arg-type]
        dimensions=16,
        context=CallContext(
            workspace_id=seeded.scope.workspace_id, document_id=None, job_id=None, attempt=1
        ),
    )


async def calls(seeded: Seeded) -> list[LlmCall]:
    async with seeded.sessionmaker() as session:
        return list(await session.scalars(select(LlmCall).order_by(LlmCall.created_at)))


async def test_ac7_embeddings_are_logged_as_task_embed(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gateway, provider = fake_gateway(seeded.sessionmaker, lambda _r: {})

    result = await gateway.embed(embed_request(seeded, "bolts", "brackets", purpose="document"))

    assert len(result.vectors) == 2
    assert all(len(vector) == 16 for vector in result.vectors)
    [call] = await calls(seeded)
    assert (call.id, call.task, call.prompt_version, call.outcome) == (
        result.call_id,
        "embed",
        "embed/document",
        "ok",
    )
    assert provider.embed_requests[0].api_key == "fake-key"  # the workspace's own key


async def test_d4_query_embeddings_are_cached_per_workspace(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    gateway, provider = fake_gateway(seeded.sessionmaker, lambda _r: {})

    first = await gateway.embed(embed_request(seeded, "packaging supplier"))
    second = await gateway.embed(embed_request(seeded, "packaging supplier"))

    assert second.vectors == first.vectors
    assert len(provider.embed_requests) == 1
    assert [call.outcome for call in await calls(seeded)] == ["ok", "cache_hit"]


async def test_no_key_and_provider_errors(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    no_keys = StaticCredentials(without={seeded.scope.workspace_id})
    gateway, _ = fake_gateway(seeded.sessionmaker, lambda _r: {}, no_keys)
    with pytest.raises(NoCredentialsError):
        await gateway.embed(embed_request(seeded, "x"))

    gateway, provider = fake_gateway(seeded.sessionmaker, lambda _r: {})
    provider.embed_error = TransientLlmError("503")
    with pytest.raises(TransientLlmError):
        await gateway.embed(embed_request(seeded, "x"))
    assert [call.outcome for call in await calls(seeded)] == ["error"]
