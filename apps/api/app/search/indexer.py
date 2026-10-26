"""Runs `embed_document` jobs: embeds a document's current extraction for search (F8 AC6).

Best-effort: without a key, or after the last retry, the document is simply found by
keyword only (AC5). Nothing here ever changes a document's status.
"""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.documents import service as documents
from app.extractions import envelope
from app.extractions import service as extractions
from app.jobs.errors import PermanentError
from app.llm.gateway import Gateway
from app.llm.types import CallContext, EmbedRequest, LlmError
from app.pipeline.steps.llm_errors import to_step_error
from app.search import repository
from app.search.embed_text import embedding_text
from app.search.models import EMBEDDING_DIMENSIONS, DocumentEmbedding


class EmbedRunner:
    def __init__(self, gateway: Gateway, *, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._gateway = gateway
        self._sessionmaker = sessionmaker

    async def run(
        self, *, workspace_id: uuid.UUID, document_id: uuid.UUID, job_id: uuid.UUID, attempt: int
    ) -> None:
        async with self._sessionmaker() as session:
            loaded = await documents.load_for_job(
                session, workspace_id=workspace_id, document_id=document_id
            )
            if loaded is None or loaded[1].current_extraction_id is None:
                return  # deleted, or nothing extracted yet
            scope, document = loaded
            extraction_id = loaded[1].current_extraction_id
            if await repository.embedded_version(session, scope, document_id) == extraction_id:
                return  # already embedded (a repeated job)
            current = await extractions.get_current(session, scope, str(document_id))
            data = await extractions.get_exact_data(session, scope, current.id)
        text = embedding_text(envelope.DOC_TYPE_BY_SCHEMA[current.schema_id], data)
        try:
            result = await self._gateway.embed(
                EmbedRequest(
                    texts=[text],
                    purpose="document",
                    dimensions=EMBEDDING_DIMENSIONS,
                    context=CallContext(
                        workspace_id=workspace_id,
                        document_id=document_id,
                        job_id=job_id,
                        attempt=attempt,
                    ),
                    use_cache=False,
                )
            )
        except LlmError as exc:
            error = to_step_error(exc, invalid_reason="Couldn't embed the document")
            if isinstance(error, PermanentError):
                return  # e.g. no key: keyword search still works, retrying won't help
            raise error from exc
        async with self._sessionmaker() as session, session.begin():
            values = {
                "workspace_id": scope.workspace_id,
                "extraction_id": current.id,
                "model": result.model,
                "embedding": result.vectors[0],
            }
            await session.execute(
                insert(DocumentEmbedding)
                .values(document_id=document.id, **values)
                .on_conflict_do_update(index_elements=[DocumentEmbedding.document_id], set_=values)
            )
