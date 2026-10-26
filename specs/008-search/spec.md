# F8: Search (spec)

**Status:** Draft (2026-10-27)
**Phase:** 4
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

Members find documents by what they contain, not just by file name. A search box on the Documents page combines two kinds of matching:

- **Keyword:** exact words and numbers (an invoice number, a GSTIN, "bolts").
- **Semantic:** meaning, from text embeddings ("packaging supplier in Delhi" finds *Yamuna Packaging Industries, Okhla*).

Filters narrow the results by type, status, vendor, date and amount. The same search powers export (F9) and, later, the MCP server (F12).

## User stories

- **US1:** As a member, I want to type an invoice number, a GSTIN or a vendor name and find the document, so that I don't scroll through lists.
- **US2:** As a member, I want to describe what I'm looking for in plain words, so that I find documents even when I don't remember the exact name.
- **US3:** As a member, I want to filter by type, status, vendor, date range and amount range, so that I can narrow a long list.
- **US4:** As the operator, I want to measure search quality on labelled queries, so that the hybrid design is justified with numbers.

## Acceptance criteria

### Searching

- **AC1:** WHEN a member searches with text, THEN the results are their workspace's documents ranked by relevance. Each result shows the document summary (type, vendor, number, date, total, status) and why it matched: **keyword**, **meaning**, or **both**.
- **AC2:** Keyword matching covers the current extraction's text fields: numbers, names, GSTINs, addresses, line-item descriptions and the file name. It is case-insensitive, and matches word prefixes (`kaver` finds *Kaveri*).
- **AC3:** Semantic matching compares an embedding of the query with an embedding of each document's current extraction. Keyword and semantic results are merged with reciprocal rank fusion, so neither score scale dominates.
- **AC4:** Filters apply with or without text: document type, status, vendor (contains), document date from–to, and total amount min–max. Results are paged (cursor, 20 per page).
- **AC5:** WHEN the workspace has no usable embedding key, or the provider fails, THEN search still answers with keyword matches only, and says "Showing keyword matches only".

### Keeping the index current

- **AC6:** WHEN a document's current extraction changes (extraction, an agent fix, or a reviewer's save), THEN its keyword index updates in the same transaction, and its embedding is recomputed by a background job.
- **AC7:** Every embedding call goes through the gateway with the workspace's own key (F15), task `embed`, and is logged like any other call (constitution §5.2). The text embedded is the extracted data, never the file.
- **AC8:** An operator command embeds documents that have none (for documents processed before F8).

### Isolation and measurement

- **AC9:** Search, filters and the vector query are always limited to the caller's workspace. A member of another workspace can never see a result, a count or a snippet from it.
- **AC10:** A search eval with labelled queries over the eval dataset reports recall@5 and MRR for keyword-only, semantic-only and hybrid search.

## Edge cases

- **Empty query and no filters:** the normal newest-first document list.
- **Documents still processing, or classified as "other":** found by file name only, until they have an extraction.
- **Very short queries** (one or two characters): keyword only, so a single letter doesn't match everything by meaning.
- **A GSTIN or number typed with spaces or lowercase:** normalised before matching.

## Non-goals

- Searching inside the original file's raw text (OCR). Only extracted data is indexed.
- Questions answered in natural language ("how much did we spend with Kaveri?"); that is the MCP server's `spend_summary` (F12).
- Saved searches and alerts.

## Decisions (proposed)

- **D1. Hybrid, in Postgres only.** Postgres full-text search (`simple` dictionary, GIN index) plus pgvector (HNSW, cosine) in the same database, merged with reciprocal rank fusion (k = 60). There's no separate search service: one more moving part would buy nothing at this scale. *Alternative:* keyword only. It's cheaper, but fails US2.
- **D2. Embedding model:** `gemini-embedding-001` at **768 dimensions** (normalised), with task type `RETRIEVAL_DOCUMENT` for documents and `RETRIEVAL_QUERY` for queries. 768 floats is about 3 KB per document, which fits the 500 MB database easily. The model id is configuration. Groq has no embeddings API, so semantic search needs a Gemini key; without one, AC5 applies.
- **D3. What is embedded:** a short text built from the current extraction, for example "Invoice INV/2026-27/0142 from Kaveri Fasteners Private Limited, Bengaluru, to …; items: steel brackets, hex bolts; total INR 16,826.80; 14 Aug 2026". It isn't the raw JSON, which embeds worse.
- **D4. Query embeddings are cached** by the gateway (per workspace, 30 days), so repeated searches cost nothing.
