# F14: Row-level security and hardening (tasks)

**Status:** Implemented (2026-10-28)
**Prerequisite:** F12 (its `api_tokens` table is covered by the RLS migration).

- [x] **F14-T1: RLS migration** (AC1, AC5): role, grants, `current_workspace()`, policies on every tenant table, meta-test. Verified against the Supabase dev project.
  - There is no Supabase database URL locally (the dev DB is Docker; Supabase serves Auth only). Instead, the migration ran in a throwaway Postgres 17 as a non-superuser owner with `CREATEROLE`, as Supabase's `postgres` is. It could switch to `docflow_app`; the owner saw both workspaces, the app role saw only its own, and with no workspace saw none. The real check is the first deploy (deploy guide §7a).
- [x] **F14-T2: Tenant and system sessions** (AC2–AC4): `after_begin` listener, `bind_workspace`, `system_session`, worker and API binding, import contract, isolation tests, full suite and metrics perf re-run.
  - `make metrics-perf` under RLS: 7 days 185 ms, 30 days 274 ms, all time 351 ms median (176, 251 and 316 ms before). Still well under 1 s.
  - An intermittent hang in the worker test suite exposed a real bug. A cancel (shutdown) that landed in a database call came back as an ordinary error, so the worker logged it and kept running forever. The worker now stops when it is being cancelled; a regression test fails without the fix. The bug was rare before F14, since RLS adds one statement per transaction, which widened the window.
- [x] **F14-T3: Idempotency keys** (AC6–AC8): table, dependency on the listed routes, web client keys, tests.
- [x] **F14-T4: Rate limiting** (AC9, AC10): token buckets, settings, 429 handling in the web app, tests.
- [x] **F14-T5: Storage cleanup** (AC11): hourly sweep, tests with fake storage.
- [x] **F14-T6: Close-out:** ADR-0009 accepted, constitution §4 updated (RLS is now the second layer), overview A3 marked done, spec status `Implemented`.
  - Live check (2026-10-28, dev stack with RLS on):
    - A fresh invoice was uploaded in the browser and processed end to end (classify, extract, validate and auto-approve; then the embedding job). Its 3 AI calls were recorded under the tenant role.
    - Both upload writes stored an idempotency key.
    - Search (4 queries) and the CSV export worked, and the Metrics page loaded.
    - No server or console errors.
