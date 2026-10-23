# DocFlow

AI document processing. Upload invoices, receipts and purchase orders, and DocFlow:

- classifies them,
- extracts structured data with a vision LLM,
- validates the data with a tool-using agent,
- sends low-confidence fields to a human reviewer, and
- exports the approved data.

> **Status:** Phase 0 (foundations). The project is built spec-first: start with the [constitution](specs/constitution.md), the [architecture overview](specs/000-architecture/overview.md) and its [ADRs](specs/000-architecture/adr/).

## Repository layout

```
specs/        specs and ADRs: the source of truth (spec.md → plan.md → tasks.md per feature)
schemas/      JSON Schemas for document types (from Phase 1)
apps/api/     FastAPI API + job worker (+ MCP later): Python 3.12, uv
apps/web/     Next.js web app: TypeScript, pnpm
docs/         deploy guide and runbooks
```

## Run it locally (macOS)

Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/) and pnpm (`brew install uv pnpm`). Node 24+.

```bash
make setup      # install dependencies and git hooks, create .env from .env.example
make db-up      # start Postgres 17 + pgvector in Docker (host port 54320)
make migrate    # apply database migrations
make dev        # API on http://localhost:8000, web on http://localhost:3000
```

Open <http://localhost:3000>. It should show **"API: ok"**. API docs are at <http://localhost:8000/docs>.

## Everyday commands

```bash
make help              # every target
make test              # API (unit + integration, with coverage) and web tests
make lint              # ruff, mypy --strict, import-linter, ESLint, Prettier, tsc
make gen               # regenerate openapi.json and the typed TS client
make check-gen         # fail if generated code is stale (CI runs this)
make migrations-check  # upgrade → downgrade → upgrade on a fresh database
make api-docker-smoke  # build the production image and smoke-test it
```

## Deploying

See [docs/deploy.md](docs/deploy.md): GitHub, Neon, Supabase, Render, Vercel and cron-job.org, all on free tiers.

## Licence

[MIT](LICENSE)
