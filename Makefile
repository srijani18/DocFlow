# DocFlow developer commands. Run `make help` for the list.
# Every target is documented with a trailing `## ` comment.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Local values (e.g. NEON_DEV_DATABASE_URL) come from the repo-root .env when present.
-include .env

API := apps/api
WEB := apps/web

.PHONY: help
help: ## List available targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- database

.PHONY: db-up db-down db-reset db-psql
db-up: ## Start local Postgres + pgvector and wait until healthy
	docker compose up -d --wait postgres

db-down: ## Stop local Postgres (data kept)
	docker compose down

db-reset: ## Delete local Postgres data and start fresh
	docker compose down -v
	$(MAKE) db-up

db-psql: ## Open psql on the local dev database
	docker compose exec postgres psql -U docflow -d docflow

# ---------------------------------------------------------------- api

.PHONY: api-lint api-fmt api-test api-test-unit
api-lint: ## Lint + type-check the API (ruff, mypy, import-linter)
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run lint-imports

api-fmt: ## Auto-format the API code
	cd $(API) && uv run ruff check --fix . && uv run ruff format .

api-test: ## Run all API tests with coverage (needs `make db-up`)
	cd $(API) && uv run pytest --cov --cov-report=term-missing

api-test-unit: ## Run API unit tests only (no Docker needed)
	cd $(API) && uv run pytest tests/unit

# ---------------------------------------------------------------- migrations

TEST_DATABASE_URL ?= postgresql://docflow:docflow@localhost:54320/docflow_test
ALEMBIC := cd $(API) && uv run alembic

.PHONY: migrate migration migrations-check migrate-neon-dev
migrate: ## Apply migrations to the local dev database (reads .env)
	$(ALEMBIC) upgrade head

migration: ## Create a migration: make migration name=add_documents
	@test -n "$(name)" || (echo "usage: make migration name=<slug>" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(name)" \
		--rev-id $$(printf "%04d" $$(( $$(ls $(API)/migrations/versions | grep -cE '^[0-9]{4}_') + 1 )))

migrations-check: ## upgrade -> downgrade base -> upgrade on the test DB, then check for model drift
	cd $(API) && export DATABASE_URL=$(TEST_DATABASE_URL) DATABASE_URL_DIRECT= && \
		uv run alembic upgrade head && uv run alembic downgrade base && \
		uv run alembic upgrade head && uv run alembic check

migrate-neon-dev: ## Rehearse migrations on the Neon dev branch (needs NEON_DEV_DATABASE_URL)
	@test -n "$(NEON_DEV_DATABASE_URL)" || (echo "Set NEON_DEV_DATABASE_URL (direct connection)" && exit 1)
	cd $(API) && DATABASE_URL=$(NEON_DEV_DATABASE_URL) DATABASE_URL_DIRECT= uv run alembic upgrade head

# ---------------------------------------------------------------- web

.PHONY: web-install web-lint web-test web-build
web-install: ## Install web dependencies
	cd $(WEB) && pnpm install --frozen-lockfile

web-lint: ## Lint, format-check and type-check the web app
	cd $(WEB) && pnpm lint && pnpm format:check && pnpm typecheck

web-test: ## Run web unit tests (Vitest)
	cd $(WEB) && pnpm test

web-build: ## Production build of the web app
	cd $(WEB) && pnpm build

# ---------------------------------------------------------------- everyday

.PHONY: setup dev dev-api dev-web lint test
setup: ## Install everything and the git hooks (first-time setup)
	cd $(API) && uv sync
	$(MAKE) web-install
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

dev: ## Run API (:8000) and web (:3000) together; needs `make db-up migrate` first
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd $(API) && uv run uvicorn app.main:create_app --factory --reload --port 8000

dev-web:
	cd $(WEB) && pnpm dev

lint: api-lint web-lint ## Lint everything

test: api-test web-test ## Test everything
