# F8: Search (tasks)

**Status:** Draft (2026-10-27)
**Prerequisite:** F7.

- [ ] **F8-T1: Keyword index** (AC2, AC6): migration `0011_search`, `search_text` written with each current-extraction change, GIN index.
- [ ] **F8-T2: Gateway embeddings** (AC7): `gateway.embed`, the Gemini `batchEmbedContents` provider call, route `embed`, logging and cache.
- [ ] **F8-T3: Embedding jobs** (AC6, AC8): the `embed` job kind, the backfill command.
- [ ] **F8-T4: Search service and endpoint** (AC1, AC3–AC5, AC9): keyword and vector queries, reciprocal rank fusion, filters, cursor, fallback.
- [ ] **F8-T5: Search UI**: search box, filter bar, match badges, notice.
- [ ] **F8-T6: Search eval** (AC10): labelled queries, recall@5 and MRR per mode, report.
- [ ] **F8-T7: Live check and close-out:** search the live-check documents by number, vendor and description; commit the eval report.
