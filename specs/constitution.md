# DocFlow Constitution

**Status:** Approved (2026-10-24)
**Applies to:** every change in this repository, by any contributor (human or AI)

These rules are not optional. To change one, edit this file in a pull request of its own and record the reason in the PR description.

---

## 1. Specs are the source of truth

1. Every feature has a folder `specs/NNN-<name>/` containing `spec.md` (what and why), `plan.md` (how) and `tasks.md` (ordered steps).
2. **No implementation before approval.** A spec is approved when its header says `Status: Approved (YYYY-MM-DD)`. Code for an unapproved spec is not merged.
3. `spec.md` contains no technology choices. Those belong in `plan.md`.
4. Every Open question is resolved or explicitly deferred (with an owner and phase) before the spec is approved.
5. **If behavior changes, the spec changes in the same PR.** A PR that changes behavior without changing `spec.md` or `plan.md` gets sent back.
6. Architecture decisions that are expensive to reverse get an ADR in `specs/000-architecture/adr/`. ADRs are never edited after acceptance; a new ADR supersedes an old one.

## 2. Testing

1. **Tests come from acceptance criteria and are written first.** Each task starts with a failing test for the criteria it names.
2. **Naming:** Python tests are named `test_ac<N>_<behavior>` (for example `test_ac13_non_member_gets_404`). Frontend tests are named `it("AC13: ...")`. Tests not tied to a criterion, such as tests for internal helpers, are named after the behavior they check.
3. **Every criterion has at least one test.** Each `plan.md` ends with a traceability table mapping criteria to tests.
4. **Test levels:**
   - *Unit tests:* no network, no database, fast.
   - *Integration tests:* run against a **real Postgres with pgvector** (Docker locally, a service container in CI). The database is never mocked.
   - *End-to-end tests:* Playwright against a running app.
5. **External services are faked at our boundary**, never deep inside our code. LLM providers are replaced by a fake provider registered in the LLM gateway. HTTP services are faked with recorded or stubbed responses. Unit and integration tests never call a real LLM or a real Supabase project.
6. **Every bug fix starts with a failing test** that reproduces the bug.
7. **Tests are deterministic.** No `sleep`-based waiting; time is frozen or injected; randomness is seeded.
8. **Coverage:** CI reports backend line coverage and fails below **80%** for `apps/api/app` (generated code excluded). The floor only goes up.

## 3. Type safety

1. Python: `mypy --strict` over `apps/api` (including tests). `Any` is allowed only at true boundaries, with a comment saying why. Every `# type: ignore[<code>]` names its error code and gives a reason.
2. TypeScript: `strict: true` plus `noUncheckedIndexedAccess`. No `any`; use `unknown` and narrow it.
3. **Validate data at runtime when it enters the system:** API input with Pydantic, LLM output against the JSON Schemas in `schemas/`, environment configuration at startup. LLM output is never trusted until it passes validation.
4. Types shared across boundaries are generated, never copied by hand: TypeScript API types come from OpenAPI, and document types come from `schemas/`.

## 4. Workspace isolation (multi-tenancy)

1. A **workspace** is the tenant. Every table holding tenant data has `workspace_id NOT NULL`, a foreign key to `workspaces`, and an index whose first column is `workspace_id`.
2. **Every query that touches tenant data filters by `workspace_id`.** Repository functions for tenant data take a `WorkspaceScope` argument, which can only be obtained from the membership-checking dependency or from a job record. Raw unscoped queries are allowed only in system code (such as the job claimer or migrations) and must carry a comment `# tenant-unscoped: <reason>`.
3. **Every tenant-scoped endpoint has an isolation test:** a member of workspace A cannot read, list, change or detect the existence of workspace B's data.
4. A request for another workspace's resource returns **404**, not 403, so the response does not reveal whether the resource exists.
5. Storage object paths start with `{workspace_id}/`. Before reading a file, workers check that the document's workspace matches the job's workspace.
6. A meta-test fails if a new table has no `workspace_id` and is not on the explicit list of global tables.
7. **Row-level security is the second layer** (F14, ADR-0009). Every tenant table has the `tenant` policy, and a meta-test fails if one doesn't. Tenant work runs as `docflow_app` for one workspace, and a session with no workspace sees nothing. Cross-workspace work goes through `app.core.rls_system`, which an import contract confines to identity, the job queue, MCP token lookup and operator tools. The `workspace_id` filters of rule 2 stay: the two layers are independent.

## 5. AI and LLM usage

1. **Every LLM call goes through the gateway** (`app/llm/`). Provider SDKs and HTTP endpoints are used only inside `app/llm/providers/`, and a lint rule enforces this.
2. **Every LLM call is logged** to `llm_calls` with: workspace, document (if any), task, provider, model, prompt version, input and output tokens, estimated cost, latency, outcome (ok, error, fallback) and attempt number.
3. **Prompts are versioned files** (`app/llm/prompts/<task>/v<N>.md`). Changing a prompt means adding a new version, so evals can compare versions.
4. Structured outputs are validated against `schemas/`. A validation failure is an explicit, logged outcome, never silently dropped.
5. **Only public datasets and synthetic documents** are used in evals, tests and demos. Workspaces process documents on their own provider keys (F15) under their own provider's terms; the upload screen still recommends sample data, because free tiers may train on what they receive.
6. **Measure before claiming.** Every accuracy, cost or latency figure in the README or in a PR cites an `eval_runs` id or a query over `llm_calls`.
7. Model IDs and rate limits are configuration, not code. Providers retire models often.

## 6. Security

1. **No secrets in the repository.** gitleaks runs in pre-commit and CI. `.env.example` lists every variable, with no real values, and is updated in the same PR that adds a variable.
2. **Least privilege:**
   - The Supabase secret key and LLM keys exist only on the backend host (Render) and in local `.env` files that git ignores.
   - The frontend receives only the Supabase URL, the publishable key and the API base URL.
3. Every endpoint requires authentication except `/healthz`, `/readyz` and the OpenAPI documentation routes.
4. Every input has a size or length limit. Uploads are limited by the storage bucket and checked again by the backend.
5. **Logs contain IDs, not personal data:** no emails, tokens, document contents or extracted values. A log processor removes known sensitive keys.
6. Dependencies are locked (`uv.lock`, `pnpm-lock.yaml`) and updated by Dependabot. Each new dependency gets a one-line justification in its PR.
7. **Customers' AI provider keys are encrypted at rest** with a server-held master key (ADR-0008), never returned by the API, never logged, and used only for that workspace's own calls.

## 7. Database and migrations

1. Every schema change is an Alembic migration. **Every migration has a working `downgrade()`.** CI runs `upgrade head → downgrade base → upgrade head` on an empty database.
2. Destructive changes follow expand/contract: add the new structure, migrate, deploy, and only then remove the old structure in a later migration.
3. The app and migrations use **one connection string**: the Supabase pooler in **session mode** (ADR-0007). DocFlow tables live in the **`docflow` schema**, never in `public`. Migrations must also run on plain Postgres, so they don't assume Supabase-only schemas or roles exist.
4. Conventions:
   - Primary keys are UUIDs.
   - Timestamps are `timestamptz` in UTC.
   - Enumerations are `text` columns with `CHECK` constraints, not Postgres enum types, because those are easier to change reversibly.
   - Constraint names follow a SQLAlchemy naming convention.
5. Migrations contain no bulk data changes. Backfills are separate, idempotent jobs.

## 8. API conventions

1. All application routes sit under `/v1`. Health routes are unversioned.
2. **Errors use RFC 9457 `application/problem+json`**, with a stable `type` URI per error kind and, for validation errors, an `errors` list naming each failing field.
3. Tenant resources live under `/v1/workspaces/{workspace_id}/...`.
4. List endpoints use cursor pagination.
5. Write endpoints that create or change something accept an `Idempotency-Key` header (F14): a repeat within 24 hours replays the first response. A new write endpoint adds the `Idempotent` dependency, or explains in its PR why it is naturally idempotent.
6. The OpenAPI document is generated by FastAPI and committed. The TypeScript client is generated from it. CI fails if either is out of date.

## 9. Reliability and free-tier discipline

1. Every call to an external service has an explicit timeout. Retries use exponential backoff with jitter and a cap.
2. Background jobs are **idempotent**: running a job twice has the same effect as running it once.
3. **Don't keep idle infrastructure awake.**
   - `/healthz` touches no dependency.
   - The worker does not poll the database while it is idle.
   - Files are never streamed through the backend to the browser.
4. Free-tier limits are written down with the date they were checked (`specs/000-architecture/overview.md` §8) and re-checked when a phase depends on them.

## 10. Observability

1. Logs are structured JSON, one event per line, carrying `request_id` and, where known, `workspace_id`, `user_id`, `document_id` and `job_id`.
2. The four headline metrics are measurable from day one (see the overview, §11):
   - extraction accuracy
   - cost per document
   - processing latency
   - share of documents approved without edits

## 11. Code style

1. **Python:**
   - ruff handles formatting and linting.
   - Each feature module contains `routes.py` (thin), `service.py` (logic), `repository.py` (SQL), `models.py` (ORM) and `schemas.py` (API models).
   - Domain logic does not import FastAPI.
2. **TypeScript:** ESLint plus Prettier, server components by default, and data fetching through TanStack Query and the generated client.
3. **Generated code is never edited by hand.** It lives in `generated/` folders and is marked `linguist-generated` in `.gitattributes`.
4. Comments explain *why*, not *what*.
5. **Prefer the simplest design that meets the acceptance criteria.** Cleverness has to earn its place in the PR description.

## 12. Git, commits and pull requests

1. **Conventional Commits**, checked by a commit-msg hook.
   - Format: `<type>(<scope>): <summary>`.
   - Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `ci`, `build`, `perf`.
   - The scope is a feature ID (`f1`) or an area (`api`, `web`, `ci`, `specs`, `schemas`).
2. **Small pull requests:** roughly 400 changed lines or fewer, excluding generated and lock files, and one or a few tasks each. Every PR links its spec and lists the criteria it covers.
3. `main` is always deployable. PRs are squash-merged and must pass CI. Branches are named `f1/t3-jwt-verifier` and similar.
4. Tick the task checkbox in `tasks.md` in the PR that completes the task.
