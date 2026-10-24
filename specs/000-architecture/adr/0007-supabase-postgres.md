# ADR-0007: Use Supabase Postgres as the only database (no Neon)

- **Status:** Accepted (2026-10-24)
- **Date:** 2026-10-24
- **Supersedes:** the Neon hosting assumptions in the overview and in ADR-0001's context (its decision, a Postgres job queue, is unchanged)

## Context

The original brief used **Neon** for Postgres and **Supabase** only for Auth and Storage. That meant two data vendors, two dashboards and two sets of free-tier limits. Neon's free plan also caps compute at 100 CU-hours a month, which forced the design to keep the database idle whenever possible.

Supabase already runs a Postgres database with pgvector for every project. On the free plan (checked 2026-10-24):

- 500 MB database
- shared compute (500 MB RAM), with no compute-hour budget
- paused after 7 days of inactivity, and restored by hand
- **no branching, no automatic backups**
- the **direct connection is IPv6-only**; the shared pooler (Supavisor) is IPv4

Render's free services can't reach IPv6 addresses.

## Decision

1. **One vendor for data:** Postgres, Auth and Storage all live in the one Supabase project. Nothing is kept in Neon.
2. **Connection:** the app and Alembic both connect through the Supabase **shared pooler in session mode** (`aws-…pooler.supabase.com:5432`, user `postgres.<ref>`). There is a single `DATABASE_URL`.
   - Session mode keeps one server connection per client connection. Prepared statements, `SET`, advisory locks and `LISTEN/NOTIFY` therefore all work. Transaction mode (port 6543) doesn't support those, and is meant for serverless clients.
   - The pool stays small (5 connections from one instance), so session mode's one-to-one mapping costs nothing.
3. **Isolation from Supabase's own surfaces:**
   - All DocFlow tables, including `alembic_version`, live in a dedicated **`docflow` schema**, never in `public`.
   - The Supabase **Data API (PostgREST) is turned off** for the project. Otherwise tables in `public` get default grants that expose them over REST to anyone holding the publishable key, and that key ships in the browser bundle.
   - The baseline migration also revokes `anon` and `authenticated` access to the `docflow` schema, as defense in depth.
4. **Users are provisioned by DocFlow, not by triggers on `auth.users`** (F1 plan §1). Our schema doesn't depend on Supabase's internal `auth` schema, so the same migrations and tests run on plain Postgres (Docker locally, and in CI).
5. **pgvector** is created `WITH SCHEMA extensions`, which is Supabase's convention. Connections set `search_path` to `docflow, extensions, public`.
6. **Local and CI** still use Docker `pgvector/pgvector:pg17`, the same major version as Supabase.

## Consequences

**Good:**
- One vendor, one dashboard and one keep-alive. Fewer secrets.
- No compute-hour budget. The worker can use a short idle sweep, and the keep-alive can call `/readyz`, so one ping keeps both Render and the database active.
- Session mode allows `LISTEN/NOTIFY`, which F3 may use to wake the worker.

**Bad:**
- **No branching:** there is no environment for rehearsing migrations. We rely on `make migrations-check` in CI, plus expand/contract migrations.
- **No automatic backups** on the free plan. The data is synthetic, so this is accepted. A scheduled `pg_dump` can be added in F14 if needed.
- **The pause after 7 idle days now takes the database down too**, not just storage and auth. It is mitigated by the keep-alive, which calls `/readyz` every 10 minutes.
- Auth, storage and data share one 500 MB database and one shared CPU. That's fine at portfolio volume.
- Local Docker Postgres isn't the Supabase image: it lacks the `auth`, `storage` and `extensions` schemas and the Supabase roles. Migrations must not assume those exist (the baseline guards its `REVOKE` behind a role check).

## Alternatives considered

- **Keep Neon for data (the original brief):** auto-wake without a manual restore, free branching and a direct IPv4 connection, but two vendors and a 100 CU-hour budget. Rejected by the project owner in favour of a single vendor.
- **Supabase transaction-mode pooler (port 6543):** suited to serverless clients. It would require turning off psycopg's prepared statements, and would rule out `LISTEN/NOTIFY` and advisory locks. Not needed for one long-running instance.
- **A second free Supabase project as staging:** it would give a place to rehearse migrations, but it's another project to keep from pausing. Deferred.
