# Sturgeon Run — developer entrypoints.
# `make up` starts the long-running stack; `make ingest` runs the one-shot job.

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

.PHONY: up
up: env ## Build and start the long-running stack (postgis, corridor-api, tiles, mcp, web)
	$(COMPOSE) up -d --build
	@echo "stack up. Run 'make ingest' to load data, then open http://localhost:5173"

.PHONY: down
down: ## Stop the stack (keeps the postgis volume)
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop the stack and DELETE the postgis volume (fresh DB next up)
	$(COMPOSE) down -v

.PHONY: ingest
ingest: env ## Run the one-shot ingest job (real GBIF + USGS -> PostGIS + quality report)
	$(COMPOSE) run --rm ingest

.PHONY: ingest-snapshot
ingest-snapshot: env ## Run ingest from cached snapshots (offline / degraded mode)
	$(COMPOSE) run --rm -e USE_SNAPSHOT=1 ingest --snapshot --source all

.PHONY: derive
derive: ## Recompute the derived corridor layer from occurrences
	@curl -fsS -X POST "http://localhost:8080/api/corridor/derive" && echo

.PHONY: smoke
smoke: ## Curl every healthcheck + MCP tools/list + one tools/call; fail loudly
	./scripts/smoke.sh

.PHONY: test
test: ## Run ingest (Python) + corridor-api (Rust) unit tests
	cd ingest && python3 -m pytest -q
	cd corridor-api && cargo test --quiet

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

.PHONY: k8s-render
k8s-render: ## Render the dev kustomize overlay (no cluster needed)
	# LoadRestrictionsNone lets base/ pull the shared db/init SQL + tiles config
	# (single source of truth) rather than duplicating them under k8s/.
	kubectl kustomize --load-restrictor LoadRestrictionsNone k8s/overlays/dev

.PHONY: k8s-apply
k8s-apply: ## Apply the dev overlay to the current kube context
	kubectl apply -k k8s/overlays/dev --load-restrictor LoadRestrictionsNone
