# F14: Row-level security and hardening (tasks)

**Status:** Draft (2026-10-27)
**Prerequisite:** F12 (its `api_tokens` table is covered by the RLS migration).

- [ ] **F14-T1: RLS migration** (AC1, AC5): role, grants, `current_workspace()`, policies on every tenant table, meta-test. Verified against the Supabase dev project.
- [ ] **F14-T2: Tenant and system sessions** (AC2–AC4): `after_begin` listener, `bind_workspace`, `system_session`, worker and API binding, import contract, isolation tests, full suite and metrics perf re-run.
- [ ] **F14-T3: Idempotency keys** (AC6–AC8): table, dependency on the listed routes, web client keys, tests.
- [ ] **F14-T4: Rate limiting** (AC9, AC10): token buckets, settings, 429 handling in the web app, tests.
- [ ] **F14-T5: Storage cleanup** (AC11): hourly sweep, tests with fake storage.
- [ ] **F14-T6: Close-out:** ADR-0009 accepted, constitution §4 updated (RLS is now the second layer), overview A3 marked done, spec status `Implemented`.
