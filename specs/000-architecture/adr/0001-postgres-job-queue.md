# ADR-0001: Use Postgres as the job queue instead of Redis

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

Document processing is asynchronous and can take tens of seconds per document, because it waits on LLM rate limits. Jobs need retries with backoff, a dead-letter state, and safe re-execution. We have one free Render instance (no background-worker services) and one Neon Postgres database. Render's free Key Value store keeps data only in memory and loses it on restart.

## Decision

Use a `jobs` table in Postgres as the queue:

- Columns: `status`, `attempts`, `max_attempts`, `run_after`, `last_error`, `idempotency_key`, `locked_at`, `locked_by`.
- Workers claim work with `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` inside a short transaction, and mark the job running together with a lease time.
- Jobs whose lease expires (because the worker crashed) become claimable again.
- After `max_attempts`, a job moves to `dead`.

The full design is in F3.

## Consequences

**Good:**
- **One fewer system** to run, monitor and keep within a free tier.
- **Transactional enqueue:** the document row and its job are committed together, so a document can never exist without its job, and a job can never point at a missing document. With a separate broker this needs an outbox pattern.
- Queue state can be queried with SQL, for debugging and for the metrics page (jobs by state, dead-letter count).
- `SKIP LOCKED` is a well-known, easy-to-explain pattern, and it is safe with several workers.

**Bad:**
- Throughput is limited by Postgres. That's acceptable at our volume (a few documents a minute), and in any case the LLM rate limits are the real bottleneck.
- The worker must not poll while idle, or Neon never suspends (overview §5). We use an in-process wake signal plus a slow sweep instead of tight polling.
- `LISTEN/NOTIFY` doesn't work through the transaction pooler, so a separate worker service (after a split) would wake by polling with backoff.

## Alternatives considered

- **Redis with RQ, Celery or arq:** needs a durable Redis, which isn't free on Render, plus an outbox for transactional enqueue.
- **A hosted queue such as SQS or Cloud Tasks:** needs a credit card, and is one more vendor.
- **A Postgres queue library such as pgmq or procrastinate:** pgmq needs an extension that may not be available on Neon's free tier. procrastinate is a reasonable choice, but writing the roughly 150 lines ourselves is cheap and gives a stronger interview story. We can revisit if the queue grows features.
