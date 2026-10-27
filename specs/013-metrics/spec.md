# F13: Metrics (spec)

**Status:** Implemented (2026-10-27)
**Phase:** 5
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

A **Metrics** page shows a workspace how DocFlow is doing on its own documents. It covers the four headline metrics of the constitution (§10.2):

- accuracy in production;
- cost per document;
- processing time;
- the share of documents approved without edits.

It also shows document volume, how reliable the AI providers are, and the health of the processing queue. Because each workspace uses its own AI keys (F15), the cost shown is the workspace's own spend, estimated at list prices.

## User stories

- **US1:** As an admin, I want to see how many documents were processed and how many needed a person, so that I know how much work DocFlow saves.
- **US2:** As an admin, I want to see what processing costs per document on my own AI key, so that I can budget.
- **US3:** As an admin, I want to see how long documents take and how often the AI provider failed or fell back, so that I can tell when something is wrong.
- **US4:** As the operator, I want the same numbers for the eval write-up, so that production can be compared with the eval set.

## Acceptance criteria

### The page

- **AC1:** A member opens **Metrics** and sees, for a chosen period (last 7 days, last 30 days, or all time), the four headline metrics:
  - **Approved without edits:** approved documents with no correction ÷ all approved documents (F7 AC8).
  - **Field accuracy in production:** fields left unchanged by reviewers ÷ all fields on human-approved documents. Agent-approved documents are counted separately, because nobody checked them.
  - **Cost per document:** estimated AI cost of processed documents ÷ their number, in USD, labelled "estimated at list prices; your provider bills you".
  - **Processing time:** median and 95th percentile from upload to the first of *Needs review*, *Approved* or *Failed*.
- **AC2:** **Volume:** documents uploaded per day as a chart. The current count by status, and by document type.
- **AC3:** **AI providers:** for each task (classify, extract, validate, embed), calls by outcome: ok, error, invalid answer, cache hit, skipped. Also the fallback rate, the share served by each provider and model, and median latency.
- **AC4:** **Queue:** jobs queued, running and dead now; the oldest queued job's age; and documents that failed in the period, with their most common reasons.
- **AC5:** Every number is limited to the member's workspace. A member of another workspace gets "not found".
- **AC6:** Numbers are computed from the data DocFlow already keeps (documents, events, extractions, corrections, LLM calls, jobs). Nothing new is recorded for metrics.
- **AC7:** The page loads in under 1 second for a workspace with 10,000 documents and 100,000 LLM calls (local measurement).

## Edge cases

- **A new workspace with no data:** each figure shows "—", with "No documents in this period".
- **A document still processing:** it isn't counted in processing time until it finishes.
- **Cache hits:** they cost $0 and count as calls.
- **Retried documents:** processing time is measured for the latest run (from its retry to its end).

## Non-goals

- Cross-workspace or operator-wide dashboards (the operator uses SQL or Langfuse, F16).
- Alerts and emails.
- Exporting the metrics.
- Real billing figures from providers.

## Decisions

- **D1. Computed on request with SQL, not stored.** The tables are indexed by workspace, and the sizes are small (AC7). A rollup table would add a job and a way to be wrong. If AC7 fails, add a materialised daily rollup then.
- **D2. Charts are plain markup** in the page, with no chart library: about 100 lines, no dependency, and readable in light and dark mode. *As built:* the one chart (uploads per day) is a row of HTML bars rather than SVG, so the rounded bar ends don't stretch when the page is resized; a hidden table carries the same numbers for screen readers.
- **D3. Who sees it:** admins and reviewers, like everything else in the workspace (F1 Q3). The numbers are about the work, not about people. Per-reviewer statistics are a non-goal.
