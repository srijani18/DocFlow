# F3: Processing pipeline (plan)

**Status:** Draft (2026-10-25)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Approach

- **Queue:** a `jobs` table in Postgres (ADR-0001). One job kind for now: `process_document`. The job and the document are created in the same transaction as the upload completion (F2), so a document can never exist without its job.
- **Worker:** the existing `app/worker` loop (`ROLE=all`), one job at a time. It claims a job with `FOR UPDATE SKIP LOCKED` and a 5-minute lease, runs the pipeline, and finishes or schedules a retry.
- **Pipeline:** an ordered list of steps in `app/pipeline/`: `fetch` (download and verify hash), `classify` (F4), `extract` (F5). Each step is **idempotent**: it first checks whether its result is already stored, and stores its result and the status change in one transaction.
- **Waking:** after the completion transaction commits, the API sets an in-process event. While idle, the worker waits on that event or until `min(next run_after, 5-minute sweep)`. No polling (AC11).
- **Live status:** each status change publishes an event to an in-process broker after commit; the SSE endpoint streams the workspace's events to its members. When API and worker split later (ADR-0002), the broker switches to Postgres `LISTEN/NOTIFY`; the interface stays the same.

## 2. API contract

```yaml
paths:
  /v1/workspaces/{workspace_id}/documents/{document_id}/retry:
    post:
      operationId: retryDocument
      responses:
        "202": { content: { application/json: { schema: { $ref: Document } } } }
        "404": {}
        "409": {}   # type not-retryable: document isn't FAILED (AC8)
  /v1/workspaces/{workspace_id}/events:
    get:
      operationId: streamEvents
      responses:
        "200":
          content:
            text/event-stream:
              # event: document.status   data: DocumentStatusEvent (JSON)
              # event: ready             data: {}      (sent on connect; the client refetches lists)
              # ": keep-alive" comment every 15 s; the server closes after 30 min
components:
  schemas:
    DocumentStatus: { enum: [UPLOADED, CLASSIFYING, EXTRACTING, NEEDS_REVIEW, FAILED] }   # F6/F7 extend
    DocumentStatusEvent: { document_id: uuid, status: DocumentStatus, failure_reason: string|null, changed_at: date-time }
    Document: { ..., status: DocumentStatus, status_changed_at: date-time }   # extends F2
```

## 3. Data model (migration `0004_jobs`)

```sql
CREATE TABLE jobs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  kind            text NOT NULL CHECK (kind IN ('process_document')),
  status          text NOT NULL CHECK (status IN ('queued','running','succeeded','dead')),
  attempts        integer NOT NULL DEFAULT 0,
  max_attempts    integer NOT NULL DEFAULT 5,
  run_after       timestamptz NOT NULL DEFAULT now(),
  locked_until    timestamptz NULL,
  locked_by       text NULL,
  last_error      text NULL,
  idempotency_key text NOT NULL UNIQUE,      -- process_document:{document_id}:{generation}
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz NULL
);
CREATE INDEX ix_jobs_workspace_id ON jobs (workspace_id);
CREATE INDEX ix_jobs_claimable ON jobs (run_after) WHERE status IN ('queued','running');

CREATE TABLE document_events (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  from_status   text NULL,
  to_status     text NOT NULL,
  job_id        uuid NULL REFERENCES jobs(id),
  detail        text NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_document_events_workspace_id ON document_events (workspace_id);
CREATE INDEX ix_document_events_document ON document_events (document_id, id);

ALTER TABLE documents
  ADD COLUMN status_changed_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN processing_generation integer NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_documents_status CHECK (status IN ('UPLOADED','CLASSIFYING','EXTRACTING','NEEDS_REVIEW','FAILED'));
```

- **One status writer:** `documents.service.transition(scope, document_id, to, ...)` updates `documents.status`, `status_changed_at` and inserts `document_events` in the caller's transaction, with a compare-and-set on the expected current status. Nothing else writes `status` (AC2).
- **Retry (AC8):** in one transaction, `UPDATE documents SET status='UPLOADED', processing_generation = processing_generation + 1 WHERE status='FAILED'` and insert a job with key `process_document:{id}:{generation}`. A double click hits the compare-and-set and gets 409 or the same job (unique key).

## 4. Claiming and finishing

```sql
-- claim (one short transaction)
UPDATE jobs SET status='running', attempts=attempts+1, locked_until=now()+interval '5 minutes',
                locked_by=:worker_id, updated_at=now()
WHERE id = (
  SELECT id FROM jobs
  WHERE (status='queued' AND run_after <= now())
     OR (status='running' AND locked_until < now())      -- abandoned lease (AC5)
  ORDER BY run_after, created_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1)
RETURNING *;
```

- **Success:** `status='succeeded', finished_at=now()`, guarded by `locked_by = :worker_id` so a worker whose lease was taken over can't overwrite the new owner's result.
- **Temporary error:** if `attempts < max_attempts`, `status='queued', run_after = now() + backoff(attempts)`; else `status='dead'` and the document transitions to `FAILED` with the last error's readable reason (AC3).
- **Permanent error:** `status='dead'` and document `FAILED` immediately (AC4).
- **Backoff:** `min(30 s · 2^(attempt−1), 15 min) · uniform(0.8, 1.2)`; if the error carries `retry_after`, use the larger.
- **Errors** are classified by type: `TransientError` (timeouts, 429, 5xx, storage unavailable) and `PermanentError` (integrity, unreadable file, unsupported). Unknown exceptions count as transient, so a bug can't fail documents permanently without the 5-attempt record.

## 5. Sequence

```mermaid
sequenceDiagram
  participant A as API
  participant DB as Postgres
  participant W as Worker
  participant S as Storage
  participant B as Browser (SSE)
  A->>DB: COMMIT document(UPLOADED) + job(queued)
  A-)W: wake
  W->>DB: claim job (SKIP LOCKED, lease 5 min)
  W->>S: download {ws}/{upload_id}
  W->>W: sha256 matches? (AC7)
  W->>DB: transition CLASSIFYING
  DB--)B: (after commit) document.status CLASSIFYING
  W->>W: classify (F4) → store
  W->>DB: transition EXTRACTING
  W->>W: extract (F5) → store version 1
  W->>DB: transition NEEDS_REVIEW; job succeeded
  DB--)B: document.status NEEDS_REVIEW
```

## 6. Components

```
app/jobs/      models.py · repository.py (claim, finish, retry_later, kill) · service.py (enqueue_for_document, retry_document) · backoff.py · errors.py
app/worker/    loop.py (wait on wake event / run_after / sweep; claim → pipeline.run → finish)
app/pipeline/  runner.py (ordered steps, idempotency checks) · steps/fetch.py (download + sha256)
app/events/    broker.py (in-process pub/sub per workspace, bounded queues) · routes.py (SSE)
web: lib/api/events.ts (fetch-based SSE reader with Bearer, reconnect with backoff) · hooks/use-document-events.ts (updates TanStack Query caches)
     components/document-status.tsx (badge) · retry button on detail page
```

- **Broker back-pressure:** each subscriber queue holds 100 events; if full, that subscriber is disconnected and reconnects (and refetches), so one slow tab can't grow memory.
- **SSE and Render:** responses set `Cache-Control: no-cache` and `X-Accel-Buffering: no`; keep-alive comments every 15 s.

## 7. Error handling

| Situation | Effect |
|---|---|
| Transient step error | Retry with backoff; `last_error` saved; document stays in its current status |
| 5th failed attempt | Job `dead`; document `FAILED`, reason e.g. "AI service unavailable after 5 attempts" |
| Permanent error | Job `dead`; document `FAILED` immediately |
| Worker crash mid-step | Lease expires; another claim resumes; idempotent steps skip finished work |
| Retry on a non-`FAILED` document | 409 `not-retryable` |

## 8. Security

- The SSE endpoint uses the same `require_workspace_member` dependency; the broker is keyed by workspace id from the scope, never from client input (AC10).
- Failure reasons shown to users are fixed, readable strings; raw exception text stays in `jobs.last_error` and logs.

## 9. Risks

| Risk | Mitigation |
|---|---|
| A long LLM call outlives the lease | Timeouts per call (60 s) and per step keep a run well under 5 minutes. |
| Open SSE tabs keep the free instance awake | Accepted: someone is actively using it. Streams close after 30 minutes. |
| In-process broker stops working after splitting roles | Documented; `LISTEN/NOTIFY` replacement behind the same interface (ADR-0002). |

## 10. Testing

- **Integration (real Postgres):** claim exclusivity with two concurrent claimers; abandoned lease reclaimed; backoff scheduling with an injected clock; dead after 5; permanent errors; idempotent re-run; retry endpoint and double-click; restart resumes queued jobs; transition writes events.
- **Worker loop:** wake on event, sleep until `run_after`, sweep; no queries while idle (count statements with a SQLAlchemy event hook).
- **SSE:** stream receives own-workspace events only (AC10); keep-alive and 30-minute close with a fake clock.
- **Web:** SSE reader parses events and reconnects; list and detail update from events (AC9).
