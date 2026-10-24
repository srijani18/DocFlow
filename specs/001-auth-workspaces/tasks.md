# F1: Auth and workspaces (tasks)

**Status:** Approved (2026-10-24)
**Prerequisite:** Phase 0 scaffold tasks P0-T1 to P0-T18 ([phase-0-tasks.md](../000-architecture/phase-0-tasks.md)).

For each task:

- write the named tests first and watch them fail;
- implement;
- run `make lint test`;
- tick the box in the same PR.

The **Done when** line is the check that the task is finished.

---

- [x] **F1-T1: Identity tables and migration** (prepares AC5, AC19)
  - Alembic `0002_identity`, creating `users`, `workspaces` and `memberships` as in plan §3, with SQLAlchemy models. Add the `two_workspaces` test fixture.
  - Meta-test `test_tenant_tables.py`: every table is either on the global allowlist or has an indexed `workspace_id NOT NULL` foreign key.
  - **Done when:** `make migrations-check` (upgrade → downgrade → upgrade) passes, and the meta-test passes.

- [x] **F1-T2: JWKS cache** (AC12, AC13)
  - `app/auth/jwks.py` with TTL caching, forced refresh on an unknown kid (throttled to once every 30 s), stale-if-error, and `AuthUnavailable`.
  - Tests:
    - `test_ac12_new_kid_triggers_refresh_and_verifies`
    - `test_ac12_removed_key_rejected_after_ttl`
    - `test_ac13_stale_keys_used_when_endpoint_down`
    - `test_ac13_no_keys_and_endpoint_down_raises_unavailable`
    - `test_unknown_kid_refresh_is_throttled`
  - **Done when:** the tests above pass using `respx` and an injected clock.

- [x] **F1-T3: Token verifier** (AC11)
  - `app/auth/verifier.py` with the algorithm allowlist and the iss, aud, exp, iat, sub, role and `is_anonymous` checks; `VerifiedClaims`.
  - Tests: one `test_ac11_*` per rejection reason (missing, malformed, expired, bad signature, wrong issuer, wrong audience, HS256, `none`, `role=anon`, anonymous user), plus a check that ES256 and RS256 are both accepted.
  - **Done when:** the tests pass, and the module imports nothing from FastAPI.

- [x] **F1-T4: Problem+json errors for authentication** (AC11, AC13)
  - Error types `unauthenticated`, `auth-unavailable` and `database-unavailable`; the `WWW-Authenticate` header; `Retry-After`. This extends the core error handlers from P0-T4.
  - Tests: `test_ac11_missing_token_returns_problem_401`, `test_ac13_auth_unavailable_returns_503_retry_after`.
  - **Done when:** the tests pass.

- [x] **F1-T5: Provisioning service** (AC5, AC6, AC7, AC8)
  - `identity/repository.py` and `identity/service.py` implementing `provision_or_load` (plan §4.3), plus `default_workspace_name`.
  - Tests:
    - `test_ac5_first_request_creates_user_workspace_admin_membership`
    - `test_ac5_failure_midway_creates_nothing`
    - `test_ac6_concurrent_first_requests_create_one_workspace`
    - `test_ac6_blocked_insert_returns_winner`
    - `test_ac7_changed_email_is_updated`
    - `test_ac8_*`: display name, email local part, the fallback, and cutting to 80 characters at a character boundary
  - **Done when:** the tests pass against real Postgres.

- [x] **F1-T6: `get_current_user` dependency and `GET /v1/me`** (AC9, AC11)
  - Tests: `test_ac9_me_returns_user_and_memberships`, `test_ac11_rejected_token_creates_nothing`.
  - **Done when:** the tests pass, and `openapi.json` is regenerated and committed.

- [ ] **F1-T7: Workspace scope and `GET /v1/workspaces/{workspace_id}`** (AC14, AC15, AC19)
  - `require_workspace_member` and `WorkspaceScope`.
  - Tests:
    - `test_ac14_member_gets_workspace_with_role`
    - `test_ac15_non_member_and_unknown_and_malformed_ids_get_identical_404`
    - `test_ac19_member_of_a_cannot_read_b`
  - **Done when:** the tests pass.

- [ ] **F1-T8: `PATCH /v1/workspaces/{workspace_id}` with role check** (AC16, AC17, AC18, AC19)
  - `require_role` and `rename_workspace(scope, name)`.
  - Tests:
    - `test_ac16_admin_renames_trimmed`
    - `test_ac17_reviewer_forbidden_name_unchanged`
    - `test_ac18_empty_whitespace_and_81_chars_rejected_with_field_error`
    - `test_ac19_admin_of_a_cannot_rename_b_gets_404`
  - **Done when:** the tests pass.

- [ ] **F1-T9: OpenAPI contract test and regenerated TypeScript client** (contract)
  - Test: `test_openapi_matches_f1_contract`, which compares the generated schemas with plan §2.
  - **Done when:** `make check-gen` is clean.

- [ ] **F1-T10: Web: Supabase clients, `proxy.ts` redirect and `safe-next`** (AC3)
  - Tests: `AC3: only /app relative paths are allowed as next`, and the redirect behaviour of `proxy.ts` (unit tested with a mocked Supabase client).
  - **Done when:** the Vitest tests pass and `pnpm build` succeeds.

- [ ] **F1-T11: Web: login page (sign in and sign up) and sign-out** (AC1, AC2, AC4)
  - shadcn form, generic error text, sign-out that clears the query cache.
  - Tests: `AC2: invalid credentials show a generic error`, `AC4: sign-out clears the session and redirects`.
  - **Done when:** the Vitest tests pass.

- [ ] **F1-T12: Web: API client auth middleware, home page and waking banner** (AC10, AC20)
  - `lib/api/client.ts`, `transient.ts` with the retry policy, `app/app/page.tsx` and `backend-waking.tsx`.
  - Tests:
    - `AC10: home shows email, workspace, role`
    - `AC20: transient errors retry up to 90s, then show Try again`
    - `client adds the Bearer token and refreshes once on 401`
  - **Done when:** the Vitest tests pass.

- [ ] **F1-T13: E2E smoke test against the deployed site** (AC1–AC4, AC10)
  - `apps/web/tests/e2e/auth.spec.ts` with a workflow `e2e-smoke.yml` (run manually and after deploy). It uses the `E2E_USER_EMAIL` and `E2E_USER_PASSWORD` GitHub secrets.
  - **Done when:** the workflow passes against production.

- [ ] **F1-T14: Close out the spec**
  - Resolve any differences found during implementation in `spec.md` and `plan.md`, and set the status to `Implemented`.
  - **Done when:** the traceability table in plan §12 matches the real test names.
