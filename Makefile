.PHONY: help install test test-unit test-functional test-infra-up test-infra-down test-infra-logs test-infra-rebuild lint format typecheck check clean serve-docs

COMPOSE_FILE = tests/infrastructure/docker-compose.yml

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

test: ## Run all tests (unit + integration)
	uv run pytest tests/unit/ tests/integration/ -v

test-unit: ## Run unit tests only
	uv run pytest tests/unit/ -v

test-integration: ## Run integration tests only
	uv run pytest tests/integration/ -v

test-all: test test-functional ## Run all tests including functional tests

test-functional: test-infra-up ## Start test infrastructure and run functional tests
	@echo "Waiting for services to be healthy..."
	@for i in $$(seq 1 30); do \
		if docker inspect --format='{{.State.Health.Status}}' pygwire_test_pg 2>/dev/null | grep -q "healthy" && \
		   docker inspect --format='{{.State.Health.Status}}' pygwire_test_proxy 2>/dev/null | grep -q "healthy"; then \
			echo "✓ Services ready"; \
			break; \
		fi; \
		if [ $$i -eq 30 ]; then \
			echo "✗ Services failed to become healthy"; \
			docker-compose -f $(COMPOSE_FILE) logs; \
			exit 1; \
		fi; \
		sleep 1; \
	done
	uv run pytest tests/proxy_functional/ -v

test-infra-up: ## Start test infrastructure (PostgreSQL + proxy)
	docker-compose -f $(COMPOSE_FILE) up -d

test-infra-down: ## Stop test infrastructure
	docker-compose -f $(COMPOSE_FILE) down

test-infra-logs: ## View test proxy logs
	docker-compose -f $(COMPOSE_FILE) logs proxy --tail 100 -f

test-infra-rebuild: ## Rebuild and restart test infrastructure
	docker-compose -f $(COMPOSE_FILE) down
	docker-compose -f $(COMPOSE_FILE) build --no-cache
	docker-compose -f $(COMPOSE_FILE) up -d

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Format code with ruff
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

typecheck: ## Run mypy type checker
	uv run mypy src/

check: lint typecheck ## Run all checks (lint + typecheck)

ci: check test ## Run all CI checks locally (lint, typecheck, tests)

serve-docs: ## Serve documentation locally
	uv run --group docs mkdocs serve

clean: ## Clean up cache and temporary files
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
