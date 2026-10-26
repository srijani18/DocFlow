"""Hybrid search (F8): keyword and meaning, merged by reciprocal rank fusion (spec D1)."""

import base64
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document
from app.search import repository
from app.search.repository import Filters
from app.search.text import to_tsquery

RRF_K = 60  # spec D1
CANDIDATES = 50  # per list, before fusion
MAX_RESULTS = 200  # how deep a cursor can page
SHORTEST_SEMANTIC_QUERY = 3  # characters (spec edge case: no meaning in one letter)
# Cosine distance beyond which a document isn't "about" the query. Tuned with the search
# eval (AC10); the same for every workspace.
MAX_DISTANCE = 0.45

Matched = Literal["keyword", "meaning", "both"]
QueryEmbedder = Callable[[str], Awaitable[list[float] | None]]


@dataclass(frozen=True)
class Hit:
    document: Document
    matched: Matched | None
    snippet: str | None


@dataclass(frozen=True)
class SearchPage:
    hits: list[Hit]
    next_offset: int | None
    semantic: bool  # False: meaning search was wanted but unavailable (AC5)


def fuse(*rankings: list[uuid.UUID]) -> list[uuid.UUID]:
    """Reciprocal rank fusion: Σ 1 / (k + rank). Ties keep the first list's order."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, document_id in enumerate(ranking, start=1):
            scores[document_id] = scores.get(document_id, 0.0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda document_id: -scores[document_id])


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def decode_cursor(cursor: str) -> int:
    """ValueError for anything that isn't a cursor this API issued."""
    text = base64.urlsafe_b64decode(cursor.encode()).decode()
    if not text.startswith("o:"):
        raise ValueError(cursor)
    offset = int(text[2:])
    if not 0 <= offset <= MAX_RESULTS:
        raise ValueError(cursor)
    return offset


async def search(  # a search has this many inputs
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    text: str,
    filters: Filters,
    offset: int,
    limit: int,
    embed_query: QueryEmbedder,
) -> SearchPage:
    tsquery = to_tsquery(text)
    if tsquery is None:
        # No text worth matching: the filtered list, newest first (spec edge case).
        ids = await repository.newest(session, scope, filters, offset=offset, limit=limit + 1)
        documents = await repository.documents_by_id(session, scope, ids[:limit])
        return SearchPage(
            hits=[Hit(document, None, None) for document in documents],
            next_offset=offset + limit if len(ids) > limit else None,
            semantic=True,
        )

    keyword = await repository.keyword_matches(session, scope, tsquery, filters, limit=CANDIDATES)
    keyword_ids = [document_id for document_id, _ in keyword]
    by_meaning = len(text.strip()) >= SHORTEST_SEMANTIC_QUERY
    vector = await embed_query(text.strip()) if by_meaning else None
    semantic_ids = (
        await repository.semantic_matches(
            session, scope, vector, filters, limit=CANDIDATES, max_distance=MAX_DISTANCE
        )
        if vector is not None
        else []
    )
    ranked = fuse(keyword_ids, semantic_ids)[:MAX_RESULTS]
    page = ranked[offset : offset + limit]
    snippets = dict(keyword)
    in_keyword, in_semantic = set(keyword_ids), set(semantic_ids)

    def matched(document_id: uuid.UUID) -> Matched:
        if document_id in in_keyword and document_id in in_semantic:
            return "both"
        return "keyword" if document_id in in_keyword else "meaning"

    documents = await repository.documents_by_id(session, scope, page)
    return SearchPage(
        hits=[
            Hit(document, matched(document.id), snippets.get(document.id)) for document in documents
        ],
        next_offset=offset + limit if offset + limit < len(ranked) else None,
        # False only when meaning search was wanted but unavailable (AC5 notice).
        semantic=vector is not None or not by_meaning,
    )
