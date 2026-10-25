# F3: Processing pipeline (spec)

**Status:** Draft (2026-10-25)
**Phase:** 1
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

After upload, each document is processed in the background: it is classified (F4), then its data is extracted (F5). Later phases add validation (F6) and review (F7). Processing survives crashes and restarts, retries temporary failures with growing delays, and gives up cleanly after a fixed number of attempts. Users see each document's status change live, without reloading.

## Statuses

`UPLOADED → CLASSIFYING → EXTRACTING → NEEDS_REVIEW`, or `FAILED` from any processing step.

- `VALIDATING` (F6) and `APPROVED` (F6/F7) are added by those features. In Phase 1, every successfully processed document ends in `NEEDS_REVIEW`.
- A document classified as "other" skips extraction and goes to `NEEDS_REVIEW` (F4 AC3).

## User stories

- **US1:** As a member, I want uploaded documents processed automatically, so that I don't wait or click anything.
- **US2:** As a member, I want to see each document's status update live, so that I know when results are ready.
- **US3:** As a member, I want a failed document to say why and let me retry it, so that a temporary problem doesn't lose my upload.
- **US4:** As the operator, I want processing to survive crashes, restarts and provider rate limits without losing or duplicating work, so that the system is trustworthy on free infrastructure.

## Acceptance criteria

- **AC1:** WHEN an upload completes (F2), THEN its document is processed in the background, moving through the statuses above, with no further user action.
- **AC2:** Every status change is recorded with its time, and the document's current status and last change time are always consistent with that record. (This feeds the latency metric, overview §11.)
- **AC3:** WHEN a processing step fails with a temporary error (provider rate limit, timeout, server error, storage unavailable), THEN it is retried after a delay that grows with each attempt. WHEN it has failed 5 times, THEN the document becomes `FAILED` with a readable reason, and the job is kept as dead for inspection.
- **AC4:** WHEN a step fails with a permanent error (unreadable or corrupt file, content that doesn't match the uploaded hash, unsupported file), THEN the document becomes `FAILED` straight away, without retries.
- **AC5:** A document is processed by at most one worker at a time. WHEN the worker stops mid-job (crash, restart, deploy), THEN the job is picked up again within 5 minutes of the worker running again, and no step's result is stored twice.
- **AC6:** Running the same job again has the same effect as running it once: a step whose result is already stored is skipped.
- **AC7:** WHEN the downloaded file's SHA-256 differs from the hash recorded at upload, THEN the document fails with "File integrity check failed" (permanent, AC4).
- **AC8:** WHEN a member clicks "Retry" on a `FAILED` document, THEN it is queued again from the first unfinished step, with a fresh set of 5 attempts. Retrying a document that isn't `FAILED` is rejected.
- **AC9:** WHEN a document's status changes, THEN members viewing the document list or that document see the new status within 2 seconds, without reloading. WHEN the live connection drops, THEN the page reconnects automatically and catches up.
- **AC10:** Status updates for workspace A are never sent to members of workspace B.
- **AC11:** WHEN there is no work, THEN the worker makes no database queries except a safety sweep every 5 minutes (constitution §9.3).
- **AC12:** WHEN the service starts, THEN jobs that were queued or interrupted before it stopped are processed without anyone re-uploading.

## Edge cases

- **Many uploads at once:** jobs run one at a time in upload order. Free LLM rate limits make parallel calls pointless on one 0.1-CPU instance.
- **Provider says "retry after N seconds":** the next attempt waits at least N seconds.
- **Retry clicked twice quickly:** one new job (AC8).
- **The service sleeps (Render free) with jobs pending:** they resume when it wakes (AC12). Phase 1 doesn't wake it on purpose; the cron keep-alive does in production.
- **A live connection left open for hours:** the server closes it after 30 minutes and the page reconnects, so connections don't pile up.

## Non-goals

- Running jobs on several instances (the design allows it later; ADR-0002).
- Priorities, scheduling, or cancelling a running job.
- Notifications (email, webhooks: F9).
- A UI for dead jobs beyond the document's `FAILED` status and reason.

## Decisions (proposed defaults; approve or change)

- **D1. Attempts and delays:** 5 attempts; delays of 30 s, 1 min, 2 min, 4 min (doubling, ±20% jitter, capped at 15 min).
- **D2. Lease:** a claimed job is held for 5 minutes; if the worker hasn't finished by then, the job can be claimed again (AC5). Every external call has a timeout well under that.
- **D3. Concurrency:** one job at a time per process.
- **D4. Live updates:** server-sent events over an authenticated `fetch` stream (the browser's `EventSource` can't send our Bearer token). Connections close after 30 minutes and reconnect.
- **D5. Retry permission:** admins and reviewers (F1 Q3).
