# F8: Search (plan)

**Status:** Approved (2026-10-27)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/search:
    get:
      operationId: searchDocuments
      parameters: q, doc_type, status, vendor, date_from, date_to, amount_min, amount_max, cursor, limit (≤ 50, default 20)
      responses:
        "200": { items: [{ document: Document, matched: keyword|meaning|both, snippet: string|null }],
                 next_cursor: string|null, semantic: bool }    # semantic=false → AC5 notice
```

Ranking is computed per request, so the cursor is an offset into the fused ranking (encoded), capped at 200 results.

## 2. Data model (migration `0011_search`)

```sql
ALTER TABLE documents ADD COLUMN search_text text NOT NULL DEFAULT '',
  ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED;
CREATE INDEX ix_documents_search ON documents USING gin (search_vector);

CREATE TABLE document_embeddings (
  document_id   uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,   -- what was embedded
  model         text NOT NULL,
  embedding     extensions.vector(768) NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_document_embeddings_workspace ON document_embeddings (workspace_id);
CREATE INDEX ix_document_embeddings_hnsw ON document_embeddings USING hnsw (embedding vector_cosine_ops);
```

`search_text` is written by `documents.set_current_extraction` (it already runs in the transaction that changes the current version, AC6). It holds the file name plus every string leaf of the data, with GSTINs and numbers also stored without spaces.

The vector query filters by `workspace_id` first, then orders by distance (`LIMIT 50`). The HNSW index is shared; isolation comes from the `WHERE` clause, as everywhere (§6 of the overview).

## 3. Components

```
app/search/      service.py (search, rrf), repository.py (keyword + vector SQL), embed_text.py, routes.py, schemas.py
app/llm/         gateway.embed(texts, task_type, context) → vectors; GeminiProvider.embed (batchEmbedContents)
app/pipeline/    an `embed` job kind (queued after extraction changes); best-effort, never fails a document
evals/search.py  labelled queries → recall@5 / MRR for keyword, semantic, hybrid (AC10)
web              Documents page: search box, filter bar, match badges; "keyword matches only" notice
```

Reciprocal rank fusion: `score = Σ 1 / (60 + rank_in_list)`. A document in both lists gets `matched = both`.

## 4. Embedding jobs

The queue (F3) already has a job `kind` and a unique `idempotency_key`. A new kind, `embed`, is enqueued in the same transaction as any current-extraction change, with the key `embed:<extraction_id>`, so repeated saves don't pile up jobs. The job embeds the document's *current* extraction; if that has changed since, it embeds the newer one. Failures retry with the normal backoff, and after the last attempt the document just stays keyword-only (AC5).

## 5. Testing

- **Unit:**
  - the embedding text from each document type;
  - reciprocal rank fusion;
  - query normalisation (GSTIN spaces, case);
  - cursor encoding.
- **Integration:**
  - keyword search on numbers, prefixes and GSTINs;
  - the vector path with a fake embedding provider;
  - hybrid merge and `matched`;
  - each filter, on its own and combined;
  - workspace isolation: same text in workspace B is never returned;
  - fallback without a key;
  - the index updated on a reviewer's save;
  - embed job idempotency.
- **Web:** search box, filters, badges, the fallback notice.
- **Eval:** 20 labelled queries over dataset v2; committed report (Phase 4 "done when", with F9).
