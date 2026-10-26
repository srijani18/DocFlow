"""Search eval (F8 AC10): recall@5 and MRR for keyword, meaning and hybrid search.

    make eval-search        # needs Docker Postgres (make db-up) and GEMINI_API_KEY

Loads dataset v2's true data into a throwaway workspace of the local test database,
embeds it with the real embedding model, runs the labelled queries through the same
search building blocks as the API, then deletes the workspace. Also reports how recall and
noise change with the meaning cut-off, which is how `MAX_DISTANCE` is chosen.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DatabaseSettings, load_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, Upload
from app.extractions import service as extractions
from app.identity.models import Membership, User, Workspace
from app.llm.circuit import CircuitBreaker
from app.llm.gateway import Gateway
from app.llm.providers.gemini import GeminiProvider
from app.llm.recording import MemoryCallRecorder
from app.llm.routing import parse_route
from app.llm.types import CallContext, EmbedRequest
from app.search import repository, service
from app.search.embed_text import embedding_text
from app.search.models import EMBEDDING_DIMENSIONS, DocumentEmbedding
from app.search.repository import Filters
from app.search.text import to_tsquery
from evals.__main__ import _commit, _env_keys
from evals.paths import MANIFEST, REPO_ROOT, REPORTS_DIR
from evals.runner import StaticKeys

QUERIES = REPO_ROOT / "evals" / "search_queries.v1.json"
TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:54320/docflow_test"
TOP = 5
CUTOFFS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
BATCH = 50  # batchEmbedContents accepts up to 100 texts


def recall_at(ranked: list[str], relevant: set[str], k: int = TOP) -> float:
    return len(set(ranked[:k]) & relevant) / min(len(relevant), k)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    return next((1 / rank for rank, doc in enumerate(ranked, 1) if doc in relevant), 0.0)


async def _load(
    session: AsyncSession, scope: WorkspaceScope, documents: list[dict[str, Any]]
) -> dict[uuid.UUID, str]:
    ids: dict[uuid.UUID, str] = {}
    for entry in documents:
        upload = Upload(
            workspace_id=scope.workspace_id,
            created_by_user_id=scope.user_id,
            filename=Path(entry["file"]).name,
            content_type=entry["content_type"],
            size_bytes=1,
            sha256=secrets.token_hex(32),
            expires_at=datetime.now(UTC),
        )
        session.add(upload)
        await session.flush()
        document = Document(
            workspace_id=scope.workspace_id,
            upload_id=upload.id,
            storage_path=f"eval/{entry['id']}",
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=1,
            sha256=upload.sha256,
            status="APPROVED",
            doc_type=entry["doc_type"],
            created_by_user_id=scope.user_id,
        )
        session.add(document)
        await session.flush()
        await extractions.record_model_extraction(
            session,
            scope,
            document_id=document.id,
            doc_type=entry["doc_type"],
            schema_id=entry["schema_id"],
            data=entry["truth"],
            confidence={},
            prompt_version="eval",
            llm_call_id=None,  # type: ignore[arg-type]  # the truth is loaded, no model call
            generation=1,
        )
        ids[document.id] = entry["id"]
    return ids


async def _embed(gateway: Gateway, texts: list[str], purpose: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        result = await gateway.embed(
            EmbedRequest(
                texts=texts[start : start + BATCH],
                purpose=purpose,  # type: ignore[arg-type]
                dimensions=EMBEDDING_DIMENSIONS,
                context=CallContext(
                    workspace_id=uuid.UUID(int=0), document_id=None, job_id=None, attempt=1
                ),
                use_cache=False,
            )
        )
        vectors += result.vectors
    return vectors


async def run(database_url: str, route: str, keys: dict[str, str]) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text())
    queries = json.loads(QUERIES.read_text())["queries"]
    settings = DatabaseSettings(database_url=database_url)
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    async with httpx.AsyncClient() as http:
        gateway = Gateway(
            sessionmaker=None,
            providers={"gemini": GeminiProvider(http=http, timeout_seconds=60)},
            routes={"embed": parse_route(route)},
            credentials=StaticKeys(keys),
            breaker=CircuitBreaker(threshold=10_000),
            recorder=MemoryCallRecorder(),
        )
        async with sessionmaker() as session:
            user = User(auth_subject=f"search-eval-{uuid.uuid4()}", email=None)
            session.add(user)
            await session.flush()
            workspace = Workspace(name="Search eval (temporary)", created_by_user_id=user.id)
            session.add(workspace)
            await session.flush()
            session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
            scope = WorkspaceScope(workspace_id=workspace.id, user_id=user.id, role="admin")
            try:
                names = await _load(session, scope, manifest["documents"])
                texts = []
                for document_id in names:
                    current = await extractions.get_current(session, scope, str(document_id))
                    data = await extractions.get_exact_data(session, scope, current.id)
                    entry = next(e for e in manifest["documents"] if e["id"] == names[document_id])
                    texts.append((document_id, current.id, embedding_text(entry["doc_type"], data)))
                vectors = await _embed(gateway, [text for _, _, text in texts], "document")
                for (document_id, extraction_id, _), vector in zip(texts, vectors, strict=True):
                    session.add(
                        DocumentEmbedding(
                            document_id=document_id,
                            workspace_id=workspace.id,
                            extraction_id=extraction_id,
                            model=route,
                            embedding=vector,
                        )
                    )
                await session.flush()
                query_vectors = await _embed(gateway, [q["q"] for q in queries], "query")
                rows = []
                for query, vector in zip(queries, query_vectors, strict=True):
                    tsquery = to_tsquery(query["q"])
                    keyword = (
                        [
                            names[i]
                            for i, _ in await repository.keyword_matches(
                                session, scope, tsquery, Filters(), limit=service.CANDIDATES
                            )
                        ]
                        if tsquery
                        else []
                    )
                    nearest = [
                        (names[i], distance)
                        for i, distance in await repository.semantic_distances(
                            session, scope, vector, Filters(), limit=service.CANDIDATES
                        )
                    ]
                    rows.append({**query, "keyword": keyword, "nearest": nearest})
            finally:
                await session.rollback()  # nothing of the eval workspace is ever committed
    await engine.dispose()
    return {"queries": rows}


def _fuse(keyword: list[str], meaning: list[str]) -> list[str]:
    ids = {name: uuid.uuid5(uuid.NAMESPACE_URL, name) for name in [*keyword, *meaning]}
    back = {value: key for key, value in ids.items()}
    return [back[i] for i in service.fuse([ids[n] for n in keyword], [ids[n] for n in meaning])]


def score(rows: list[dict[str, Any]], cutoff: float) -> dict[str, dict[str, float]]:
    modes: dict[str, list[tuple[float, float]]] = {"keyword": [], "meaning": [], "hybrid": []}
    for row in rows:
        relevant = set(row["relevant"])
        meaning = [name for name, distance in row["nearest"] if distance <= cutoff]
        for mode, ranked in (
            ("keyword", row["keyword"]),
            ("meaning", meaning),
            ("hybrid", _fuse(row["keyword"], meaning)),
        ):
            modes[mode].append((recall_at(ranked, relevant), reciprocal_rank(ranked, relevant)))
    return {
        mode: {
            "recall_at_5": sum(r for r, _ in values) / len(values),
            "mrr": sum(m for _, m in values) / len(values),
        }
        for mode, values in modes.items()
    }


def noise(rows: list[dict[str, Any]], cutoff: float) -> float:
    """Average number of irrelevant documents within the cut-off, per query."""
    return sum(
        sum(1 for name, d in row["nearest"] if d <= cutoff and name not in row["relevant"])
        for row in rows
    ) / len(rows)


def to_markdown(meta: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    current = service.MAX_DISTANCE
    lines = [
        f"# Search eval `{meta['run_id']}`",
        "",
        f"- **Commit:** `{meta['commit']}` · **Dataset:** v2 · **Queries:** {len(rows)} "
        f"({sum(r['kind'] == 'exact' for r in rows)} exact, "
        f"{sum(r['kind'] == 'meaning' for r in rows)} by meaning) · "
        f"**Embeddings:** `{meta['route']}`, {EMBEDDING_DIMENSIONS} dimensions · "
        f"**Created:** {meta['created_at']}",
        f"- Recall@5 counts the relevant documents in the top 5 (out of at most 5); MRR is "
        f"1 / rank of the first relevant one. Meaning cut-off: cosine distance ≤ {current}.",
        "",
        "## Summary",
        "",
        "| Mode | Recall@5 | MRR | Recall@5 (exact) | Recall@5 (meaning) |",
        "|---|---|---|---|---|",
    ]
    overall = score(rows, current)
    exact = score([r for r in rows if r["kind"] == "exact"], current)
    meaning = score([r for r in rows if r["kind"] == "meaning"], current)
    for mode in ("keyword", "meaning", "hybrid"):
        lines.append(
            f"| {mode} | **{overall[mode]['recall_at_5']:.0%}** | {overall[mode]['mrr']:.2f} | "
            f"{exact[mode]['recall_at_5']:.0%} | {meaning[mode]['recall_at_5']:.0%} |"
        )
    lines += [
        "",
        "## Choosing the meaning cut-off",
        "",
        "| Cosine distance ≤ | Hybrid recall@5 | Hybrid MRR "
        "| Irrelevant documents within the cut-off, per query |",
        "|---|---|---|---|",
    ]
    for cutoff in CUTOFFS:
        hybrid = score(rows, cutoff)["hybrid"]
        mark = " (current)" if cutoff == current else ""
        lines.append(
            f"| {cutoff:.2f}{mark} | {hybrid['recall_at_5']:.0%} | {hybrid['mrr']:.2f} | "
            f"{noise(rows, cutoff):.1f} |"
        )
    lines += [
        "",
        "## Per query",
        "",
        "| Query | Kind | Keyword | Meaning | Hybrid |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        relevant = set(row["relevant"])
        meaning_ranked = [n for n, d in row["nearest"] if d <= current]
        cells = [
            f"{recall_at(r, relevant):.0%}"
            for r in (row["keyword"], meaning_ranked, _fuse(row["keyword"], meaning_ranked))
        ]
        lines.append(f"| {row['q']} | {row['kind']} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.search")
    parser.add_argument(
        "--database-url", default=os.environ.get("EVAL_DATABASE_URL", TEST_DATABASE_URL)
    )
    parser.add_argument("--out", default=str(REPORTS_DIR))
    args = parser.parse_args(argv)
    keys = _env_keys()
    if "gemini" not in keys:
        print("Skipping the search eval: no GEMINI_API_KEY")
        return 0
    route = load_settings().llm_route_embed
    result = await run(args.database_url, route, keys)
    created = datetime.now(UTC)
    commit = _commit()
    meta = {
        "run_id": f"search-{created:%Y%m%d-%H%M}-{commit}-{secrets.token_hex(2)}",
        "commit": commit,
        "created_at": created.isoformat(timespec="seconds"),
        "route": route,
        "max_distance": service.MAX_DISTANCE,
    }
    print(f"wrote {_write(Path(args.out), meta, result)}")
    return 0


def _write(out: Path, meta: dict[str, Any], result: dict[str, Any]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{meta['run_id']}.json").write_text(json.dumps({**meta, **result}, indent=2) + "\n")
    markdown = out / f"{meta['run_id']}.md"
    markdown.write_text(to_markdown(meta, result["queries"]))
    return markdown


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
