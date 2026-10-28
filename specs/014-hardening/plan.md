# F14: Row-level security and hardening (plan)

**Status:** Implemented (2026-10-28)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md) · **ADR:** [0009](../000-architecture/adr/0009-row-level-security.md)

## 1. RLS in the database (migration `0013_row_level_security`)

```sql
-- once per cluster (idempotent: role names are cluster-wide, shared by dev and test DBs)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'docflow_app') THEN
    CREATE ROLE docflow_app NOLOGIN NOBYPASSRLS;
  END IF;
END $$;
GRANT docflow_app TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;  -- PG16+ grant options
GRANT USAGE ON SCHEMA docflow TO docflow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA docflow TO docflow_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA docflow TO docflow_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA docflow GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO docflow_app;

CREATE FUNCTION docflow.current_workspace() RETURNS uuid STABLE LANGUAGE sql
  AS $$ SELECT nullif(current_setting('docflow.workspace_id', true), '')::uuid $$;

-- for each tenant table T (generated from the same list the meta-test checks):
ALTER TABLE docflow.T ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON docflow.T TO docflow_app
  USING (workspace_id = docflow.current_workspace())
  WITH CHECK (workspace_id = docflow.current_workspace());
-- workspaces: USING (id = docflow.current_workspace()); users stays global (no RLS).
```

- **Owner bypasses RLS.** The table owner (the migration user) isn't subject to RLS without `FORCE`. That is exactly the system context: system sessions simply don't `SET ROLE`.
- **No policies for `anon`/`authenticated`** (AC5). RLS on, no policy for them, so they get nothing. A test checks it on the local DB, where those roles are created for the test.
- **The test DB.** The test user is a superuser; `SET ROLE docflow_app` drops superuser powers for the transaction, so RLS applies in tests exactly as in production.
- **Checked locally (2026-10-27, Postgres 17, rolled back):** with this role, grant and policy, the owner sees all rows, the app role with no workspace sees none, with workspace A sees only A's, and inserting a B row is refused.
- **Risk.** On Supabase, `postgres` has `CREATEROLE` but isn't a superuser. The `GRANT … WITH SET TRUE` is needed (PG16+ no longer grants it by default). This is verified against the Supabase dev project before merging.

## 2. RLS in the application (`app/core/db.py`, `app/core/tenancy.py`)

- **Tenant sessions.** `session.info["workspace_id"]` drives an `after_begin` listener that runs `SET LOCAL ROLE docflow_app` and `SELECT set_config('docflow.workspace_id', :ws, true)` at the start of every transaction. A workspace set mid-transaction is applied at once, through `bind_workspace(session, scope)`.
- **Default is tenant with no workspace** (fail closed, D2). The listener runs `SET LOCAL ROLE docflow_app` even without a workspace.
- **System sessions.** `system_session(sessionmaker)` marks `session.info["system"] = True`, and the listener skips the role. It is used only by:
  - `app.identity` (membership resolution, provisioning, `/v1/me`);
  - `app.jobs.queue` (claim, sweep, next due);
  - `app.core.health`;
  - the worker's hourly sweeps (§3, §5);
  - CLIs (`evals`, `search.backfill`, `metrics_perf`).

  An import-linter contract allows `system_session` only there.
- **API.** `WorkspaceScopeDep` resolves the membership in a system sub-transaction, then `bind_workspace`. Everything after it in the request is tenant-bound.
- **Worker.** Pipeline steps and runners receive the job's workspace and open sessions with `tenant_sessionmaker(workspace_id)`. The gateway's call recorder and cache use the call's `workspace_id`.

## 3. Idempotency (`app/core/idempotency.py`)

```
idempotency_keys (tenant table): workspace_id, user_id, key (≤ 255 chars), method, path,
  request_hash (sha256 of body), status ('running'|'done'), response_status, response_body jsonb,
  created_at; unique (workspace_id, user_id, key)
```

- **A dependency on each listed route:**
  1. insert a `running` row in its own transaction (`ON CONFLICT DO NOTHING`);
  2. if the row exists: same hash and `done` replays the stored response; `running` gives 409; a different hash gives 422;
  3. after the handler, the response is stored in the request's transaction, so the business change and the record commit together.
- **Expiry.** Rows older than 24 h are deleted by the worker sweep.
- **Without the header,** behaviour is unchanged (the header is optional, as clients may not send it).

## 4. Rate limiting (`app/core/ratelimit.py`)

- **Token buckets** keyed by `(user or token id, bucket)`, in memory, with `asyncio`-safe updates.
- **Buckets and settings** (defaults):

  | Bucket | Default |
  |---|---|
  | `general` | 120/min |
  | `uploads` | 30/min |
  | `ai` | 30/min (search queries, key tests) |
  | `mcp` | 60/min |

- **Applied** as a route dependency, so it runs after authentication. Answers 429 with `Retry-After`.
- **Not limited:** `/healthz`, `/readyz`, the SSE stream.

## 5. Storage cleanup (worker sweep)

Hourly, as a system operation:
- select uploads with `expires_at < now() - 1h` and no `document_id`;
- delete their objects in batches of 100 (Supabase Storage bulk delete);
- mark them cleaned (`cleaned_at`);
- delete rows older than 7 days.

## 6. Web

- An `Idempotency-Key` per mutation (`crypto.randomUUID()` kept across the cold-start retries).
- A 429 message using `Retry-After`.

## 7. Testing

- **Meta-test:** every tenant table has RLS enabled, a `tenant` policy and grants to `docflow_app` (AC1).
- **Isolation:** for each tenant table, an unfiltered `SELECT` under workspace A's scope returns no B rows, an `INSERT` of a B row is refused, and a session with no workspace sees zero rows (AC2, AC3).
- **Full suite** with RLS on (AC4), plus `make metrics-perf` re-run (the tenant role, the setting and the policy add a cost to each query, which is checked).
- **Idempotency:** replay, 422 on a changed body, 409 while running, expiry.
- **Rate limit:** 429 after N, `Retry-After`, buckets independent.
- **Cleanup:** expired uploads' files deleted, documents' files untouched.

## 8. As built (2026-10-28)

- **Context variable plus listener.** The workspace a task acts for is a context variable, set by the API's workspace dependency (`bind_workspace`), by the worker per job (`acting_for`) and by each MCP tool. The `after_begin` listener applies it in **one** statement per transaction: `set_config('role', …, true)` and `set_config('docflow.workspace_id', …, true)`.
  - Precedence: an explicit system session, then the context variable, then a system session maker's default (operator tools, tests' seeding), then fail closed.
  - System transactions issue no statement unless the connection's current transaction had switched role (tracked in `connection.info`).
  - The request middleware resets the context variable per request.
- **System operations:** `identity.provision_or_load` and `identity.list_memberships` switch themselves to system. The worker's job claim and next-due query use `system_session`, as do the MCP token lookup, the hourly maintenance and the CLIs (`system_sessionmaker`). A new (eighth) import contract forbids `app.core.rls_system` everywhere else; it was confirmed to catch a planted import.
- **The membership check runs under RLS.** The workspace dependency binds the path's workspace **before** checking membership, so a non-member simply finds no membership row.
- **`extensions` usage:** `docflow_app` needs `USAGE` on the `extensions` schema for pgvector's types and operators (found by the search tests).
- **Idempotency** is a route dependency (claim, in its own committed transaction) plus an `IdempotentRoute` class (store the 2xx response, or release the key on error). A row left `running` by a crash is ignored after a minute.
- **Rate limits.**
  - The general limit is checked in `get_current_user`, so every authenticated request counts, except the event stream (path suffix).
  - Route dependencies apply the uploads and AI buckets. Search and export count against the AI bucket only when they have query text.
  - MCP is limited per token in its auth wrapper.
- **Cleanup** is `app/worker/maintenance.py`, run by the worker loop at most hourly. A new `uploads.cleaned_at` column (migration 0015) records deleted files, so each is deleted once. The Supabase client got a bulk `delete`.
