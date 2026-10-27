# F13: Metrics (tasks)

**Status:** Implemented (2026-10-27)
**Prerequisite:** F7, F10.

- [x] **F13-T1: Metrics queries** (AC1–AC6): headline, volume, LLM, queue; integration tests with known answers.
- [x] **F13-T2: Endpoint** (AC1, AC5): `GET …/metrics?period=`, schemas, isolation.
- [x] **F13-T3: Metrics page** (AC1–AC4): tiles, the uploads chart, provider table, queue panel, sidebar item.
- [x] **F13-T4: Performance check** (AC7): seed 10k documents / 100k calls locally, time the endpoint, add an index if needed.
  - `make metrics-perf` (2026-10-27, local Docker Postgres 17, 5 runs per period): 7 days median 176 ms, 30 days 251 ms, all time 316 ms; slowest single run 432 ms (the first, cold). **Pass**, so no new index or migration was needed.
- [x] **F13-T5: Live check and close-out:** the live-check workspace's real numbers on the page; spec status `Implemented`.
  - 2026-10-27, dev stack, real data: 1 approved (with 1 correction, so 0% without edits), field accuracy 42/43 = 98%, $0.0038 per document over 7 documents, median processing 1.1 min (p95 10.4 min, which includes the runs that hit Gemini 503s), 4 AI tasks all served by Gemini, 1 dead job. The period switch, chart hover and no console errors were checked in Chromium.
