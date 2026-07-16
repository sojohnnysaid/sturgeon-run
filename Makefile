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
derive: ## Recompute the derived corridor layer for EVERY species
	# Multi-species: derive per species_id so each taxon gets its own corridor.
	@ids=$$(curl -fsS "http://localhost:8080/api/species" \
		| grep -oE '"id"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+'); \
	test -n "$$ids" || { echo "no species found (run 'make ingest' first)"; exit 1; }; \
	for id in $$ids; do \
		echo -n "  species_id=$$id -> "; \
		curl -fsS -X POST "http://localhost:8080/api/corridor/derive?species_id=$$id" && echo; \
	done

.PHONY: smoke
smoke: ## Curl every healthcheck + MCP tools/list + one tools/call; fail loudly
	./scripts/smoke.sh

.PHONY: test
test: test-python test-rust ## Run ingest (Python, in Docker) + corridor-api (Rust) unit tests

.PHONY: test-python
test-python: ## Run the Python validator tests inside the ingest image (no host Python needed)
	# Self-provisioning: pytest ships in ingest/requirements.txt, so the tests run
	# INSIDE the ingest image. `make test` therefore needs NO host Python packages
	# (only Docker) and passes identically on a clean machine and in CI.
	$(COMPOSE) build ingest
	docker run --rm --entrypoint python \
		-e PYTHONDONTWRITEBYTECODE=1 \
		-v "$(CURDIR)/ingest/tests:/app/tests:ro" \
		sturgeon-run/ingest -m pytest -q -p no:cacheprovider tests

.PHONY: test-rust
test-rust: ## Run the corridor-api Rust query-param tests (needs cargo)
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
