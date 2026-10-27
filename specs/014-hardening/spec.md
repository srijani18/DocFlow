# F14: Row-level security and hardening (spec)

**Status:** Draft (2026-10-27)
**Phase:** 6
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md) · **ADR:** [0009](../000-architecture/adr/0009-row-level-security.md)

## Summary

Workspace isolation gets a **second, independent layer**: Postgres row-level security (RLS). Today every query filters by `workspace_id` in the application (constitution §4). After F14, the database itself refuses to return or change another workspace's rows, even if a query forgets the filter (overview decision A3). RLS also blocks Supabase's own Data API roles from every table.

F14 also delivers the hardening items earlier specs deferred to it:
- **`Idempotency-Key` enforcement** on write endpoints (constitution §3.5);
- **rate limiting** (F1, F12);
- **cleanup of files from abandoned uploads** (F2).

## User stories

- **US1:** As a workspace owner, I want the database itself to keep my documents from other workspaces, so that one missed filter in the code can't leak them.
- **US2:** As a member on a flaky connection, I want a retried upload, approval or key change to happen once, so that I never get duplicates.
- **US3:** As the operator, I want a runaway client or script limited, so that one user can't exhaust the free instance or someone's AI quota.
- **US4:** As the operator, I want storage to hold only files that belong to documents, so that the free 1 GB isn't used up by abandoned uploads.

## Acceptance criteria

### Row-level security

- **AC1:** Every tenant table has RLS enabled, with a policy allowing rows only of the **current workspace**, for reads and writes. A meta-test fails if a table with `workspace_id` lacks it.
- **AC2:** Application work on tenant data runs as a database role that **can't bypass RLS**, with the current workspace set per transaction. A query that leaves out the `workspace_id` filter still returns only the current workspace's rows: a test proves it on each tenant table.
- **AC3:** **Fail closed:** a session with no workspace set sees **no** tenant rows and can write none. Only named system operations, listed in the plan and enforced by an import contract, run without RLS:
  - resolving a signed-in user's memberships;
  - provisioning a new user;
  - claiming and sweeping jobs across workspaces;
  - health checks;
  - migrations and operator CLIs.
- **AC4:** Every existing test passes with RLS on, and the metrics check (F13 AC7) stays under 1 s.
- **AC5:** Supabase's Data API roles (`anon`, `authenticated`) can read nothing in the `docflow` schema, even if the Data API is turned back on.

### Idempotency

- **AC6:** POST and DELETE endpoints that create or change something accept an `Idempotency-Key` header:
  - start and complete upload;
  - retry;
  - approve;
  - save, test and remove an AI key;
  - create and revoke an access token.

  A repeat of the same key, by the same user, with the same request within 24 hours returns the **original response** (status and body) with `Idempotent-Replayed: true`, and does nothing again.
- **AC7:** The same key with a different request body returns **422** (`idempotency-key-reused`). A repeat that arrives while the first is still running returns **409** (`idempotency-key-in-progress`), with `Retry-After`.
- **AC8:** The web app sends a new key per user action and the same key on its automatic retries (cold starts, F1 AC20).

### Rate limiting

- **AC9:** Requests are limited per user and per access token, with separate limits for uploads, AI-backed calls (search queries, AI key tests) and MCP tool calls. Each limit is configurable.
- **AC10:** Over a limit, the API answers **429** problem+json with `Retry-After`, and the web app shows "Too many requests, try again in N s". Health checks and the event stream are never limited.

### Storage cleanup

- **AC11:** Files of uploads that were never completed are deleted from storage within 24 hours of the upload expiring. Their upload rows are deleted after 7 days. Files of documents are never touched.

## Edge cases

- **A user in two workspaces:** each request sets the workspace from its URL. Listing one's own memberships (`/v1/me`) is a system operation (AC3).
- **The worker:** each job sets its document's workspace before touching tenant data; claiming the next job is a system operation.
- **Two tabs approving the same document with the same key:** one approves, and the other gets the replayed response.
- **The API restarts:** rate-limit counters reset (in memory, D3); idempotency records survive (in Postgres).

## Non-goals

- A CAPTCHA on sign-up (Supabase supports Cloudflare Turnstile): the Supabase built-in sign-up rate limits are enough for a demo.
- An audit log of sign-ins: Supabase Auth already keeps one (`auth.audit_log_entries`, visible in the dashboard).
- Automated database backups (ADR-0007: data is synthetic).
- A distributed rate limiter (one API instance, ADR-0002).

## Decisions (proposed)

- **D1. RLS with a non-owner role and a per-transaction setting** (ADR-0009): the migration creates `docflow_app` (NOLOGIN, NOBYPASSRLS). Tenant transactions run `SET LOCAL ROLE docflow_app` and `set_config('docflow.workspace_id', …, true)`. Policies compare `workspace_id` with that setting. This is safe with the session pooler, because `SET LOCAL` ends with the transaction.
- **D2. Fail closed by default.** Sessions are tenant sessions unless explicitly opened as system sessions, so forgetting to bind a workspace returns nothing rather than everything.
- **D3. Rate limits in process memory** (token buckets), since there is one API process (ADR-0002). A second instance would need Postgres or Redis counters; that is recorded as a known limit.
- **D4. Idempotency records in Postgres** (`idempotency_keys`, a tenant table under RLS too), kept for 24 hours and pruned by the worker's sweep.
