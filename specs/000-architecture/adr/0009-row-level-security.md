# ADR-0009: Row-level security as a second isolation layer

**Status:** Accepted (2026-10-28)
**Feature:** [F14](../../014-hardening/spec.md)

## Context

Workspace isolation is enforced in the application: every repository takes a `WorkspaceScope` and filters by `workspace_id` (constitution §4), and the tests check it. That is one layer: a single query that forgets the filter leaks data across workspaces. Overview decision A3 deferred Postgres row-level security to F14 as defense in depth.

Constraints:
- The API reaches Supabase Postgres through the **session-mode pooler**, as the `postgres` role, which owns the tables.
- Owners bypass RLS unless it is forced.
- `postgres` on Supabase is not a superuser, but can create roles.
- Some work legitimately spans workspaces: resolving a user's memberships at sign-in, claiming the next job from the shared queue, health checks, migrations.

## Decision

1. **A non-owner role, `docflow_app`** (NOLOGIN, NOBYPASSRLS), with DML grants on the `docflow` schema. The connection user is granted `SET` on it.
2. **One policy per tenant table:** `workspace_id = docflow.current_workspace()` for reads and writes, where `current_workspace()` reads the transaction-local setting `docflow.workspace_id`.
3. **Each transaction declares its tenant:** `SET LOCAL ROLE docflow_app` and `set_config('docflow.workspace_id', <id>, true)`, from a SQLAlchemy `after_begin` listener driven by `session.info`. `SET LOCAL` ends with the transaction, so a pooled connection never carries one request's tenant into the next.
4. **Fail closed:** a session that sets no workspace still switches to `docflow_app` and sees nothing.
5. **System sessions** don't switch role, so as the owner they bypass RLS. They are opened only through `system_session()`, which an import-linter contract confines to the identity, queue, health and CLI modules.
6. **Application filters stay.** RLS is the second layer, not a replacement; repositories keep their `workspace_id` filters and the existing isolation tests.

## Alternatives considered

- **A login role per tenant, or `FORCE ROW LEVEL SECURITY` on the owner:** more roles, or every system query rewritten as a policy exception; no benefit at this size.
- **Supabase's `auth.uid()` policies through the Data API:** the API doesn't use the Data API, and per-user policies would duplicate the membership logic in SQL.
- **Session-level `SET` (not `LOCAL`):** leaks between pooled connections unless every return to the pool is reset. Too easy to get wrong.
- **Only the application layer (status quo):** one missed filter is a cross-tenant leak.

## Consequences

- **Every query** runs under a role switch and a policy check. The cost is measured with the F13 performance check (F14 AC4).
- **A new tenant table must be added to the policy list.** The meta-test fails until it is.
- **Debugging in `psql`** needs `SET ROLE docflow_app; SELECT set_config('docflow.workspace_id', '…', false);` to see what the app sees. The deploy guide documents it.
- **Supabase's Data API roles** get no access to `docflow` tables, even if the Data API is re-enabled.
