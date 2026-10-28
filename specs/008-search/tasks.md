# F8: Search (tasks)

**Status:** Implemented (2026-10-27)
**Prerequisite:** F7.

- [x] **F8-T1: Keyword index** (AC2, AC6): migration `0011_search`, `search_text` written with each current-extraction change, GIN index.
- [x] **F8-T2: Gateway embeddings** (AC7): `gateway.embed`, the Gemini `batchEmbedContents` provider call, route `embed`, logging and cache.
- [x] **F8-T3: Embedding jobs** (AC6, AC8): the `embed` job kind, the backfill command.
- [x] **F8-T4: Search service and endpoint** (AC1, AC3–AC5, AC9): keyword and vector queries, reciprocal rank fusion, filters, cursor, fallback.
- [x] **F8-T5: Search UI**: search box, filter bar, match badges, notice.
- [x] **F8-T6: Search eval** (AC10): labelled queries, recall@5 and MRR per mode, report.
  - Run [`search-20261026-2006-4fa0ed0-2279`](../../evals/reports/search-20261026-2006-4fa0ed0-2279.md): hybrid recall@5 **95%**, MRR 1.00. Keyword alone: 50% (100% on exact queries, 0% on descriptions).
  - The first run ([`…-990a`](../../evals/reports/search-20261026-2005-4fa0ed0-990a.md)) showed that a fixed cut-off (cosine distance ≤ 0.45) left about 20 unrelated documents per query.
  - Meaning matches are now kept within 0.04 of the closest document, capped at 0.45: about 1.2 unrelated documents per query.
- [x] **F8-T7: Live check and close-out:** search the live-check documents by number, vendor and description; commit the eval report.
  - **Done (2026-10-27), locally with the smoke-test workspace's own Gemini key, in a real browser:**
    1. `make search-backfill` re-indexed 6 existing documents and queued 6 embeddings. The worker embedded them with `gemini-embedding-001` (6 `embed` calls logged, all `ok`).
    2. Searches:
       - "kaveri" found the 3 Kaveri invoices by keyword.
       - "packaging company in Delhi" found only the Yamuna Packaging invoice, by meaning.
       - "south indian breakfast" found the two tiffin-centre receipts, by meaning.
       - "INV/2025-14/6450" found its invoice.
  - The live check showed snippets built from the index text, which read badly ("2026 09 18 20260918 INV 2025 14 6450 …"). Snippets now name the field that matched: "Invoice number: [[INV/2025-14/6450]]".
