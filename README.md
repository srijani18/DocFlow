# DocFlow

AI document processing. Upload invoices, receipts and purchase orders, and DocFlow:

- classifies them,
- extracts structured data with a vision LLM,
- validates the data with a tool-using agent,
- sends low-confidence fields to a human reviewer, and
- exports the approved data.

> **Status:** Phases 0–2 done (foundations, the processing pipeline, multi-provider LLM gateway and evals); Phase 3 (validation agent and human review) in progress. The project is built spec-first: start with the [constitution](specs/constitution.md), the [architecture overview](specs/000-architecture/overview.md) and its [ADRs](specs/000-architecture/adr/).

## Accuracy

Measured by the eval suite ([F11](specs/011-evals/spec.md)) on dataset v1: 30 labelled documents (20 synthetic invoices, receipts and purchase orders, half of them rendered as noisy photos, plus 10 real receipts from CORD v2). Baseline run [`20261026-1656-5e6f28f-acd5`](evals/reports/20261026-1656-5e6f28f-acd5.md):

| Model | Classification | Field accuracy | Documents with every field right | Median latency | Cost / document* |
|---|---|---|---|---|---|
| Gemini Flash-Lite (`gemini-flash-lite-latest`, served as 3.5) | 100% | **97.6%** | 63% | 43 s | $0.0049 |
| Gemini 3.1 Flash-Lite | 100% | 94.6% | 37% | 9 s | n/a |

\*At list prices; on the free tier it costs nothing. The default route uses Flash-Lite 3.5. It's slower, but most accurate, especially on addresses. Real receipts are the hard part: 79–80% field accuracy on CORD against 96–99% on synthetic documents.

An earlier run, scored before missing CORD labels were masked, measured 97.7% and 94.2%: on 30 documents, expect differences of up to about a point between runs. Run `make eval` to reproduce; reports land in [`evals/reports/`](evals/reports/).

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

**Signing in locally** uses a free Supabase project for Auth (the database stays in Docker). Do steps 2a and 2c–2f of [docs/deploy.md](docs/deploy.md) (skip 2b), set `Site URL` to `http://localhost:3000`, then put the project URL in `SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL`, and the publishable key in `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, in `.env`.

**AI processing uses your own keys** (bring your own key). Set `BYOK_MASTER_KEYS` in `.env` to the output of `make byok-key`, then open **Settings** in the app and connect a Gemini key (free at <https://aistudio.google.com/apikey>). Groq and OpenRouter keys are optional fallbacks.

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

See [docs/deploy.md](docs/deploy.md): GitHub, Supabase (database, auth, storage), Render, Vercel and cron-job.org, all on free tiers.

## Licence

[MIT](LICENSE)
