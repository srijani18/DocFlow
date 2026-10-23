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
