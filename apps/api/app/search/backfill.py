"""Brings documents processed before F8 into search (AC8).

    make search-backfill

Rewrites each document's keyword text from its current extraction, and queues an embedding
for every document whose embedding is missing or older than its current version. Run it
by the operator after deploying F8; it's safe to run again.
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.tenancy import WorkspaceScope
from app.documents.models import Document
from app.extractions import service as extractions
from app.jobs import service as jobs
from app.models import import_all_models
from app.search.models import DocumentEmbedding
from app.search.text import search_terms

OPERATOR_ROLE = "operator"


async def backfill(session: AsyncSession) -> tuple[int, int]:
    """(documents re-indexed, embeddings queued)."""
    # tenant-unscoped: an operator command over every workspace; each write is scoped below.
    rows = await session.execute(
        select(Document, DocumentEmbedding.extraction_id)
        .outerjoin(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
        .where(Document.current_extraction_id.is_not(None))
    )
    indexed = queued = 0
    for document, embedded in rows.all():
        assert document.current_extraction_id is not None  # noqa: S101  # filtered above
        scope = WorkspaceScope(
            workspace_id=document.workspace_id,
            user_id=document.created_by_user_id,
            role=OPERATOR_ROLE,
        )
        current = await extractions.get_current(session, scope, str(document.id))
        data = await extractions.get_exact_data(session, scope, current.id)
        document.search_text = search_terms(data)
        indexed += 1
        if embedded != document.current_extraction_id and await jobs.enqueue_embedding(
            session, scope, document_id=document.id, extraction_id=current.id
        ):
            queued += 1
    return indexed, queued


async def main() -> int:
    import_all_models()  # the ORM needs every table to resolve foreign keys
    engine = create_engine(load_settings())
    async with create_sessionmaker(engine)() as session, session.begin():
        indexed, queued = await backfill(session)
    await engine.dispose()
    print(f"re-indexed {indexed} documents, queued {queued} embeddings (the worker runs them)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
