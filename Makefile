# DocFlow developer commands. Run `make help` for the list.
# Every target is documented with a trailing `## ` comment.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Local values come from the repo-root .env when present.
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
	docker compose exec postgres psql -U postgres -d docflow

# ---------------------------------------------------------------- api

.PHONY: api-lint api-fmt api-test api-test-unit api-docker api-docker-smoke
api-lint: ## Lint + type-check the API (ruff, mypy, import-linter)
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run lint-imports

api-fmt: ## Auto-format the API code
	cd $(API) && uv run ruff check --fix . && uv run ruff format .

api-test: ## Run all API tests with coverage (needs `make db-up`)
	cd $(API) && TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest --cov --cov-report=term-missing

api-test-unit: ## Run API unit tests only (no Docker needed)
	cd $(API) && uv run pytest tests/unit

api-docker: ## Build the API Docker image (docflow-api:local)
	docker build -f $(API)/Dockerfile -t docflow-api:local .

api-docker-smoke: ## Build the image, run it against a throwaway Postgres, check health
	$(API)/scripts/docker-smoke.sh

# ---------------------------------------------------------------- migrations

TEST_DATABASE_URL ?= postgresql://postgres:postgres@localhost:54320/docflow_test
ALEMBIC := cd $(API) && uv run alembic

.PHONY: migrate migration migrations-check
migrate: ## Apply migrations to the local dev database (reads .env)
	$(ALEMBIC) upgrade head

migration: ## Create a migration: make migration name=add_documents
	@test -n "$(name)" || (echo "usage: make migration name=<slug>" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(name)" \
		--rev-id $$(printf "%04d" $$(( $$(ls migrations/versions | grep -cE '^[0-9]{4}_') + 1 )))

migrations-check: ## upgrade -> downgrade base -> upgrade on the test DB, then check for model drift
	cd $(API) && export DATABASE_URL=$(TEST_DATABASE_URL) && \
		uv run alembic upgrade head && uv run alembic downgrade base && \
		uv run alembic upgrade head && uv run alembic check


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
	cd $(API) && uv run pre-commit install

dev: ## Run API (:8000) and web (:3000) together; needs `make db-up migrate` first
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd $(API) && uv run uvicorn app.main:create_app --factory --reload --port 8000

dev-web:
	cd $(WEB) && pnpm dev

lint: api-lint web-lint ## Lint everything

test: api-test web-test ## Test everything

# ---------------------------------------------------------------- code generation (constitution §3.4)

GENERATED := $(API)/openapi.json $(WEB)/src/generated $(API)/app/generated

.PHONY: gen gen-openapi gen-schemas check-gen
gen: gen-openapi gen-schemas ## Regenerate OpenAPI, the TS client and schema models

gen-openapi:
	cd $(API) && uv run python -m app.openapi
	cd $(WEB) && pnpm --silent gen:api

# The generators get a copy of schemas/ with only the .json files (the README isn't a schema).
SCHEMAS_TMP := $(shell mktemp -d 2>/dev/null || echo /tmp/docflow-schemas)
gen-schemas:
	@if ls schemas/documents/*.json >/dev/null 2>&1; then \
		rsync -a --delete --include='*/' --include='*.json' --exclude='*' schemas/ $(SCHEMAS_TMP)/ && \
		rm -rf $(API)/app/generated/schemas $(WEB)/src/generated/schemas && \
		(cd $(API) && uv run datamodel-codegen --input $(SCHEMAS_TMP) --input-file-type jsonschema \
			--output app/generated/schemas --output-model-type pydantic_v2.BaseModel \
			--target-python-version 3.12 --use-standard-collections --use-union-operator \
			--field-constraints --disable-timestamp --use-schema-description --formatters builtin \
			--custom-file-header '# Generated from schemas/ by `make gen-schemas`. Do not edit.') && \
		(cd $(SCHEMAS_TMP) && for f in $$(find . -name '*.json' | sort); do \
			out=$(CURDIR)/$(WEB)/src/generated/schemas/$${f%.json}.d.ts; mkdir -p $$(dirname $$out); \
			(cd $$(dirname $$f) && $(CURDIR)/$(WEB)/node_modules/.bin/json2ts -i $$(basename $$f) -o $$out \
				--bannerComment '/* Generated from schemas/ by make gen-schemas. Do not edit. */') || exit 1; \
		done); \
		rm -rf $(SCHEMAS_TMP); \
	else echo "schemas/: no document schemas yet, nothing to generate"; fi

check-gen: gen ## Fail if generated code is out of date
	@git diff --quiet -- $(GENERATED) && \
		test -z "$$(git ls-files --others --exclude-standard -- $(GENERATED))" || \
		(echo "Generated code is out of date: run 'make gen' and commit the result." && exit 1)

.PHONY: eval eval-dataset eval-import search-backfill
MODELS ?= gemini:gemini-flash-lite-latest
LIMIT ?=
PACE ?= 0
eval: ## Run evals (F11): make eval MODELS=gemini:…,groq:… LIMIT=20 PACE=4 AGENT=1 [MANIFEST=…]
	cd $(API) && uv run python -m evals --models "$(MODELS)" $(if $(LIMIT),--limit $(LIMIT)) --pace $(PACE) $(if $(AGENT),--agent) $(if $(MANIFEST),--manifest $(abspath $(MANIFEST)))

search-backfill: ## F8: index and queue embeddings for documents processed before search existed
	cd $(API) && uv run python -m app.search.backfill

eval-import: ## Approved documents of YOUR workspace → eval data (F7): make eval-import WORKSPACE=<id>
	@test -n "$(WORKSPACE)" || (echo "usage: make eval-import WORKSPACE=<your workspace id>" && exit 1)
	cd $(API) && uv run python -m evals.import_reviews --workspace "$(WORKSPACE)"

eval-dataset: ## Rebuild evals/dataset v2 (synthetic + broken documents; CORD kept or downloaded)
	cd $(API) && uv run python -m evals.build_dataset

.PHONY: byok-key
byok-key: ## Print a new BYOK master key for BYOK_MASTER_KEYS (F15, ADR-0008)
	@cd $(API) && uv run python -c "from app.aikeys.crypto import generate_master_key; print(generate_master_key())"

.PHONY: pre-commit
pre-commit: ## Run every pre-commit hook on all files
	cd $(API) && uv run pre-commit run --all-files
