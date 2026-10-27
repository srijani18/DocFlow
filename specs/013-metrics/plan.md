# F13: Metrics (plan)

**Status:** Draft (2026-10-27)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/metrics:
    get:
      operationId: getWorkspaceMetrics
      parameters: period (7d | 30d | all, default 30d)
      responses:
        "200":
          headline: { approved: int, approved_without_edits: int, approved_by_agent: int,
                      fields_reviewed: int, fields_unchanged: int,
                      documents_processed: int, cost_usd: decimal | null,
                      processing_seconds_p50: number | null, processing_seconds_p95: number | null }
          volume: { per_day: [{date, uploaded}], by_status: {…}, by_doc_type: {…} }
          llm: [{ task, outcome_counts: {…}, fallback_share, by_model: [{provider, model, calls}],
                  latency_ms_p50 }]
          queue: { queued, running, dead, oldest_queued_seconds, failures: [{reason, documents}] }
```

The existing `GET …/metrics/review` (F7) stays as it is; the dashboard tile keeps using it.

## 2. Queries (`app/metrics/repository.py`)

Every query starts with `workspace_id = :ws`. Each answers one block, so the page makes four small queries, not one large one.

- **Processing time:** for each document, the latest `UPLOADED` event (a retry starts a new run) to the first later event into `NEEDS_REVIEW`, `APPROVED` or `FAILED`. Uses `percentile_cont(0.5 / 0.95)` over the period.
- **Production accuracy:** rows in `corrections` per document, against the number of scalar fields in its approved version. Only documents approved by a person count. The field count is computed in SQL from the JSONB with `jsonb_path_query`.
- **Cost:** `sum(cost_usd)` of `llm_calls` with a `document_id` in the period, divided by the number of distinct documents.
- **LLM block:** a `GROUP BY task, outcome`, plus `provider, model`.
- **Queue:** counts by status, plus `min(created_at)` of queued jobs. Failures are grouped by `documents.failure_reason`.

New index: `llm_calls (workspace_id, created_at)` (migration `0012_metrics_indexes`), if the AC7 measurement needs it.

## 3. Web

`/app/metrics`: the period switch, four stat tiles, a volume bar chart (SVG), the provider table, and the queue panel. A new "Metrics" item goes in the sidebar.

## 4. Testing

- **Integration:** each block, using seeded documents, events, corrections, calls and jobs with known answers. Also: workspace isolation, the empty workspace, a retried document's processing time, and the period boundaries.
- **Performance:** a local script seeds 10,000 documents and 100,000 calls, then times the endpoint (AC7). The result goes in the tasks file.
- **Web:** tiles and "—" for empty data, the period switch, and the chart rendering bars with accessible labels.
