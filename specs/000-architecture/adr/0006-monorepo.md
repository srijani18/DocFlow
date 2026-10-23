# ADR-0006: Use one monorepo instead of separate repos

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

`schemas/` is the single source of truth for document shapes. It feeds the backend (generated Pydantic models), the frontend (generated TypeScript types), the LLM (response schemas) and the evals. The frontend's API client is generated from the backend's OpenAPI spec. Many changes touch the specs, the schema, the backend and the frontend at the same time.

## Decision

1. **One repository** containing `specs/`, `schemas/`, `apps/api` (uv), `apps/web` (pnpm), `evals/` and `docs/`.
2. No cross-language monorepo tool (Nx, Turborepo, Bazel). A root `Makefile` provides the common commands: `setup`, `dev`, `test`, `lint`, `gen`, `check-gen`.
3. CI uses path filters, so each pull request runs only the jobs for the paths it changed. Deploys use build filters: Render builds on changes to `apps/api/**` and `schemas/**`, and Vercel on `apps/web/**`.

## Consequences

**Good:**
- **Atomic changes:** a schema change, the regenerated code on both sides and the spec update land in one reviewed commit.
- CI can prove the generated code is up to date (`make check-gen`), so the API and the UI can't drift apart.
- One place for specs, ADRs and history, which is easy for reviewers and interviewers to follow.

**Bad:**
- Path-filtered CI needs care: a required "all checks" job must pass even when some jobs are skipped.
- Two toolchains (Python and Node) in one repo. A Makefile and pre-commit keep developer commands uniform.

## Alternatives considered

- **Separate repos for frontend, backend and schemas:** schema changes would need versioned packages and coordinated releases, which is heavy for one developer and invites drift.
- **Turborepo or Nx:** useful for many JavaScript packages. With one Python app and one JavaScript app, the added complexity isn't worth it.
