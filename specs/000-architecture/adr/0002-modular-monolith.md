# ADR-0002: Build a modular monolith instead of microservices

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24

## Context

There is one developer and one free Render web service (512 MB, 0.1 CPU, no worker services). The product has clear sub-domains: identity, documents, jobs and pipeline, the LLM gateway, search, export and MCP. Running separate services would multiply cold starts, deploys, configuration and network failure modes, with no benefit at this scale.

## Decision

1. **One deployable** (`apps/api`) containing the API, the worker and the MCP server. The process role comes from `ROLE=api|worker|all`.
2. **Enforced module boundaries:**
   - Each feature module (`identity`, `documents`, `jobs`, `pipeline`, `llm`, `search`, `export`, `mcp`) exposes a `service.py` facade.
   - Other modules import only that facade (plus `core` and `auth`).
   - An `import-linter` contract in CI enforces this.
3. **No shared mutable in-process state** between the API and the worker, apart from the optional wake signal. Everything goes through Postgres, so splitting the roles across separate processes stays safe.

## Consequences

**Good:**
- One build, one deploy, one log stream, and in-process calls that are trivial to test.
- Running `ROLE=all` on a single free instance fits Render's limits.
- **Splitting is a configuration change:** deploy the same image twice, with `ROLE=api` and `ROLE=worker`.

**Bad:**
- A CPU-heavy job can slow API responses in `ROLE=all`. This is mitigated by keeping CPU work small (LLMs do the heavy work remotely), giving the worker a concurrency limit, and avoiding local ML models.
- A crash takes down both the API and the worker. Both restart together, and the job leases recover work that was in progress.
- Module boundaries depend on discipline plus a lint contract, not on network separation.

## Alternatives considered

- **Microservices (API, worker, gateway):** not possible on the free tier without several instances, and it adds operational cost with no gain at this volume.
- **A serverless worker (Vercel or Cloudflare functions):** execution-time limits and cold starts clash with long LLM calls, and it splits the codebase across runtimes.
