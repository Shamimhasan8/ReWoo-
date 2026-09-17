# =============================================================
# ReWoo Development Makefile
# =============================================================
# Usage: make <target>
# Help:  make help
# =============================================================

.PHONY: help install dev-install test lint format typecheck \
        docker-up docker-down docker-build \
        db-migrate db-upgrade clean

# ---- Defaults ----
PYTHON      ?= python
PIP         ?= pip
DOCKER      ?= docker
COMPOSE     ?= docker compose

# ---- Help (default target) ----
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- Install ----
install: ## Install package (production)
	$(PIP) install --upgrade pip && \
	$(PIP) install .

dev-install: ## Install package with dev dependencies
	$(PIP) install --upgrade pip && \
	$(PIP) install -e ".[dev]"

dev-install-all: ## Install with all optional deps
	$(PIP) install --upgrade pip && \
	$(PIP) install -e ".[dev,k8s]"

# ---- Testing ----
test: ## Run test suite
	pytest -v

test-cov: ## Run tests with coverage report
	pytest --cov=rewoo --cov-branch --cov-report=term-missing --cov-report=html -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v

test-api: ## Run API tests only
	pytest tests/api/ -v

# ---- Linting & Formatting ----
lint: ## Run ruff linter
	ruff check .

lint-fix: ## Run ruff linter with auto-fix
	ruff check --fix .

format: ## Format code with ruff
	ruff format .

format-check: ## Check formatting without changes
	ruff format --check .

typecheck: ## Run mypy type checking
	mypy rewoo/

# ---- Docker ----
docker-build: ## Build all Docker images
	$(COMPOSE) build

docker-up: ## Start all services
	$(COMPOSE) up -d

docker-down: ## Stop all services
	$(COMPOSE) down

docker-logs: ## Tail service logs
	$(COMPOSE) logs -f api

docker-restart: ## Restart all services
	$(COMPOSE) restart

docker-ps: ## List running services
	$(COMPOSE) ps

# ---- Database ----
db-migrate: ## Create a new migration
	alembic -c rewoo/db/migrations/alembic.ini revision --autogenerate -m "$(msg)"

db-upgrade: ## Apply all pending migrations
	alembic -c rewoo/db/migrations/alembic.ini upgrade head

db-downgrade: ## Rollback one migration
	alembic -c rewoo/db/migrations/alembic.ini downgrade -1

db-current: ## Show current migration version
	alembic -c rewoo/db/migrations/alembic.ini current

# ---- Cleanup ----
clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .eggs/
	rm -rf __pycache__/ rewoo/__pycache__/ tests/__pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml
	rm -rf *.so
