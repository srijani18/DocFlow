# DocFlow developer commands. Run `make help` for the list.
# Every target is documented with a trailing `## ` comment.

SHELL := /bin/bash
.DEFAULT_GOAL := help

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
