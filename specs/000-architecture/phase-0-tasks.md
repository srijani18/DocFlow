# Phase 0: Scaffold tasks (not part of F1)

**Status:** Approved (2026-10-24)
**Phase goal (done when):** you can sign in on the live production URL, and CI is green.

## Order of work

1. P0-T1 to P0-T18: the scaffold, plus a placeholder deployed to production.
2. F1-T1 to F1-T14: sign-in and workspaces ([tasks](../001-auth-workspaces/tasks.md)).
3. P0-T19: final verification.

We deploy before F1 so that authentication is built against the real hosting from the start.

Each task lists its **Done when** check. Tasks that set up tooling are tested by running that tooling (for example, CI itself, or `docker build` plus a smoke request).

---

- [x] **P0-T1: Repository initialisation**
  - `git init` on `main`.
  - `.gitignore` covering Python, Node, `.env*` (except `.env.example`), `.DS_Store` and Playwright output.
  - `.gitattributes`, marking `*/generated/**`, `openapi.json` and lock files as `linguist-generated`.
  - `.editorconfig`, a README stub, `LICENSE` (overview A8), and a `Makefile` skeleton with a `help` target (later tasks add targets).
  - **Done when:** `make help` lists the targets, and `git status` is clean after the first commit.

- [x] **P0-T2: `docker-compose.yml` with Postgres and pgvector**
  - Image `pgvector/pgvector:pg17`, with the same major version as Neon (overview A7). Host port `54320` by default (override with `DOCFLOW_PG_PORT`), so it does not clash with other local Postgres instances.
  - A named volume, port `5432`, and a health check (`pg_isready`).
  - An init script that creates the `docflow` and `docflow_test` databases and enables `vector` in both.
  - Targets `make db-up`, `make db-down` and `make db-reset`.
  - **Done when:** `make db-up` makes the container healthy, and `SELECT extversion FROM pg_extension WHERE extname='vector'` returns a row in both databases.

- [x] **P0-T3: API project scaffold and settings**
  - `apps/api` as a uv project pinned to Python 3.12.
  - `pyproject.toml` configuring ruff (lint and format), `mypy --strict` (with the pydantic plugin), and pytest (`asyncio_mode=auto`, markers `unit` and `integration`, coverage floor 80%).
  - `app/core/config.py` using `pydantic-settings`, with typed and validated settings, failing fast with a list of missing variables.
  - The root `.env.example` documents every setting.
  - Tests:
    - `test_settings_missing_required_vars_fails_fast_with_names`
    - `test_env_example_lists_every_setting` (a parity check between `Settings` fields and `.env.example`)
  - **Done when:** `make api-lint api-test` passes.

- [x] **P0-T4: Core cross-cutting behaviour (logging, request ID, errors)**
  - JSON logs with `structlog`, with a processor that redacts sensitive keys (`authorization`, `email`, `token`, `password`, and so on).
  - Request-ID middleware (accepts or generates `X-Request-ID` and echoes it back).
  - Problem+json handlers for validation errors, `HTTPException`, our own `AppError` hierarchy and unhandled exceptions.
  - Tests:
    - `test_request_id_is_echoed_and_generated`
    - `test_validation_error_is_problem_json_with_field_errors`
    - `test_unhandled_error_is_problem_500_with_request_id_and_no_stack`
    - `test_redaction_processor_masks_sensitive_keys`
  - **Done when:** the tests pass.

- [x] **P0-T5: `/healthz` and `/readyz`**
  - `/healthz` returns 200 `{"status":"ok"}` without touching any dependency.
  - `/readyz` runs `SELECT 1` with a 5 s timeout, returning 200, or 503 problem+json.
  - Tests:
    - `test_healthz_ok_without_database` (the database URL points to a closed port)
    - `test_readyz_ok_with_database`
    - `test_readyz_503_when_database_unreachable`
  - **Done when:** the tests pass.

- [x] **P0-T6: `ROLE` switch and entrypoint**
  - `create_app(settings)` mounts the HTTP routers for `api` and `all`, and starts a placeholder worker task in the app's lifespan for `all`.
  - `python -m app` runs uvicorn for `api` and `all`, and runs only the worker loop (no HTTP server) for `worker`.
  - In Phase 0, the worker does nothing and does **not** touch the database. It waits on a wake event and logs a heartbeat once an hour.
  - Shutdown cancels the worker cleanly.
  - Tests:
    - `test_role_api_has_routes_and_no_worker`
    - `test_role_all_starts_and_stops_worker_cleanly`
    - `test_role_worker_runs_without_http`
    - `test_invalid_role_fails_fast`
  - **Done when:** the tests pass.

- [x] **P0-T7: Database layer**
  - SQLAlchemy 2.1 async engine using **psycopg 3**, a session-per-request dependency, and a naming convention for constraints.
  - Pool settings for Neon's pooler: `pool_size=5`, `max_overflow=0`, `pool_pre_ping=True`, `pool_recycle=300`, `connect_timeout=10`. Connection failures (Neon waking, network blips) become `503 database-unavailable` with `Retry-After: 5`, and the client retries (F1 AC20). There is no hidden retry on the server, so all retrying happens in one place.
  - Why psycopg 3: one driver serves both the async app and synchronous Alembic, and it works with Neon's pooled connection string.
  - Sessions are injected through the `DbSession` alias (`Depends(get_session, scope="function")`), so the commit runs *before* the response is sent. With FastAPI's default scope, a failed commit would still return 200.
  - Tests: `test_session_dependency_commits_and_rolls_back`, `test_failed_commit_is_an_error_response_not_200` (integration), `test_unreachable_database_maps_to_503` (unit).
  - **Done when:** the test passes.

- [x] **P0-T8: Alembic setup and baseline migration**
  - Async `env.py`, which reads **`DATABASE_URL_DIRECT`** (falling back to `DATABASE_URL` locally), and revision IDs of the form `NNNN_<name>`.
  - `0001_baseline`: `CREATE EXTENSION IF NOT EXISTS vector`; the downgrade drops it.
  - `make migrations-check`: upgrade head → downgrade base → upgrade head on a fresh `docflow_test`, plus `alembic check` to catch model drift.
  - `make migrate-neon-dev`, for rehearsing migrations on the Neon `dev` branch (overview A2).
  - **Done when:** `make migrations-check` passes.

- [ ] **P0-T9: Test infrastructure**
  - `tests/conftest.py` with: a session-scoped migrated test database; a rollback-per-test session; a `committing_db` fixture (truncates after each test) for concurrency tests; an `httpx.AsyncClient` against the ASGI app; and a frozen clock.
  - `tests/unit` and `tests/integration` folders, so `make api-test-unit` runs without Docker.
  - **Done when:** a sample integration test proves that data from one test isn't visible in the next.

- [ ] **P0-T10: Module boundary rules**
  - An `import-linter` contract:
    - Feature modules import each other only through `service.py`.
    - `app/llm/providers` is imported only by `app/llm`.
    - Domain `service.py` files don't import `fastapi`.
  - A ruff `banned-api` rule for provider SDKs outside `app/llm/providers/`.
  - **Done when:** `lint-imports` passes in `make api-lint`, and a deliberately bad import (tried locally) fails it.

- [ ] **P0-T11: Next.js app scaffold**
  - `apps/web` created by `create-next-app`, with: App Router, TypeScript `strict` and `noUncheckedIndexedAccess`, Tailwind v4, ESLint, and the `src/` directory.
  - Prettier, `shadcn` init (button, card, input, label, tabs, sonner), and a TanStack Query provider.
  - Vitest with Testing Library and jsdom; a Playwright config with an empty test folder.
  - `src/env.ts` validating the `NEXT_PUBLIC_*` variables with zod.
  - A placeholder landing page showing the name "DocFlow" and the current API health, fetched from `/healthz`.
  - TypeScript version: whatever `typescript-eslint` currently supports (overview §8).
  - Tests: `landing shows API status ok/unavailable` (Vitest).
  - **Done when:** `pnpm lint && pnpm typecheck && pnpm test && pnpm build` passes.

- [ ] **P0-T12: Code generation pipeline**
  - `python -m app.openapi` writes `apps/api/openapi.json` without starting a server.
  - `openapi-typescript` generates `apps/web/src/generated/api.d.ts`; `lib/api/client.ts` wraps it with `openapi-fetch`.
  - The `schemas/` step (datamodel-code-generator and json-schema-to-typescript) is wired up, but does nothing while there are no schema files.
  - `make gen` runs everything; `make check-gen` runs `make gen` and then `git diff --exit-code`.
  - **Done when:** `make check-gen` passes on a clean tree, and fails after a route change that wasn't regenerated (tried locally).

- [ ] **P0-T13: Pre-commit hooks**
  - `.pre-commit-config.yaml` with:
    - ruff (lint and format), and mypy (as a local hook through uv)
    - ESLint, Prettier and `tsc --noEmit` (local hooks through pnpm, only on `apps/web/**`)
    - gitleaks
    - check-yaml, check-json, end-of-file-fixer, trailing-whitespace and check-added-large-files (500 KB)
    - `conventional-pre-commit` on commit-msg
  - `make setup` installs the hooks.
  - **Done when:** `pre-commit run --all-files` passes, and a commit message `bad message` is rejected.

- [ ] **P0-T14: CI workflow (`.github/workflows/ci.yml`)**
  - Runs on `pull_request` and on pushes to `main`. A `changes` job uses `dorny/paths-filter` with three filters:
    - `api`: `apps/api/**`, `schemas/**`
    - `web`: `apps/web/**`, `schemas/**`
    - `infra`: `.github/**`, `docker-compose.yml`, `render.yaml`
  - Jobs:
    - `api-lint`: ruff, mypy, import-linter
    - `api-test`: unit and integration tests with a `pgvector/pgvector:pg17` service container, plus coverage
    - `api-migrations`: `make migrations-check`
    - `api-docker`: `docker build`, then run the container and curl `/healthz`
    - `web-lint`: ESLint and tsc
    - `web-test`: Vitest
    - `web-build`: `next build`
    - `codegen-check`: `make check-gen`
    - `secrets`: gitleaks, always runs
  - A final **`ci-ok`** job depends on all the others and succeeds when each one either succeeded or was skipped. Branch protection and Render's "after CI checks pass" use this job.
  - uv and pnpm caches are turned on.
  - **Done when:** the first PR shows a green `ci-ok`, and a PR that only changes `apps/web` skips the `api-*` jobs.

- [ ] **P0-T15: Dockerfile and start script (`apps/api`)**
  - A multi-stage build: the uv builder image installs `--frozen --no-dev` into `/app/.venv`; the runtime image is `python:3.12-slim`, running as a non-root user.
  - The build copies the needed `schemas/` files into the image; the build context is the repo root.
  - `start.sh` runs `alembic upgrade head` and then `exec python -m app`. Uvicorn uses one worker, the `$PORT` variable, proxy headers and the `ROLE` variable.
  - **Done when:**
    - `make api-docker` builds and runs the image, and `/healthz` returns 200;
    - the image is under 250 MB;
    - idle memory is under 200 MB (`docker stats`), leaving room within Render's 512 MB.

- [ ] **P0-T16: `render.yaml` and Vercel config**
  - `render.yaml` defines one web service:
    - `runtime: docker`, `plan: free`, `region: singapore`
    - `dockerfilePath: apps/api/Dockerfile`, `dockerContext: .`
    - `healthCheckPath: /healthz`
    - `autoDeployTrigger: checksPass`
    - `buildFilter.paths: [apps/api/**, schemas/**]`
    - `envVars`, with `sync: false` for every secret and `ROLE=all`
  - `apps/web/vercel.json` with an `ignoreCommand` that skips the build when `apps/web` hasn't changed.
  - **Done when:** the Render Blueprint validates (by previewing it in the Render dashboard), and the Vercel project builds from `apps/web`.

- [ ] **P0-T17: `docs/deploy.md` and the local-setup README**
  - `docs/deploy.md`: the step-by-step manual checklist, covering accounts, regions, connection strings, Supabase keys and settings, the bucket, environment variables per platform, cron-job.org, branch protection and rollback.
  - README: what DocFlow is, how to run it locally (`make setup db-up dev`), and links to the specs.
  - **Done when:** following `docs/deploy.md` from scratch works without needing to ask anything (checked during P0-T18).

- [ ] **P0-T18: First production deploy (placeholder)**
  - You create the accounts and set the secrets (the checklist from P0-T17); I check the result.
  - **Done when:**
    - `https://<render-service>.onrender.com/healthz` returns 200;
    - `/readyz` returns 200 (Neon reachable, migration `0001` applied);
    - the Vercel production URL shows the landing page with "API: ok".

- [ ] **P0-T19: Phase 0 verification (after F1)**
  - Run the F1 E2E smoke workflow against production.
  - cron-job.org: a `/healthz` ping every 10 min, and a weekly Supabase request, both running.
  - CI green on `main`.
  - **Done when:**
    - you can sign up and sign in on the production URL and see your workspace and role;
    - `ci-ok` is green.
