"""FastAPI wiring for query embeddings. Tests override `get_query_embedder`."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.logging import get_logger
from app.core.tenancy import WorkspaceScope
from app.llm.gateway import Gateway
from app.llm.types import CallContext, EmbedRequest, LlmError
from app.search.models import EMBEDDING_DIMENSIONS
from app.search.service import QueryEmbedder

log = get_logger(__name__)

QueryEmbedderFactory = Callable[[WorkspaceScope], QueryEmbedder]


def gateway_query_embedder(gateway: Gateway) -> QueryEmbedderFactory:
    def for_scope(scope: WorkspaceScope) -> QueryEmbedder:
        async def embed(text: str) -> list[float] | None:
            try:
                result = await gateway.embed(
                    EmbedRequest(
                        texts=[text],
                        purpose="query",
                        dimensions=EMBEDDING_DIMENSIONS,
                        context=CallContext(
                            workspace_id=scope.workspace_id,
                            document_id=None,
                            job_id=None,
                            attempt=1,
                        ),
                    )
                )
            except LlmError as exc:
                # No key, or the provider is down: keyword matches only (AC5).
                log.info("query_embedding_unavailable", error_type=type(exc).__name__)
                return None
            return result.vectors[0]

        return embed

    return for_scope


def get_query_embedder(request: Request) -> QueryEmbedderFactory:
    factory: QueryEmbedderFactory = request.app.state.query_embedder
    return factory


QueryEmbedderDep = Annotated[QueryEmbedderFactory, Depends(get_query_embedder)]
