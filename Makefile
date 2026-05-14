.PHONY: all reproduce build up down download-data download-models \
        test lint loadtest demo regenerate clean help

# Default Python for local (non-Docker) targets
PYTHON ?= python

# Docker Compose project name
COMPOSE = docker compose

# ---------------------------------------------------------------
# High-level targets
# ---------------------------------------------------------------

all: help

## reproduce: Full reproducibility check — build, download, pipeline, test, coverage
reproduce: build download-data download-models
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/unit/ \
	    --tb=short -q \
	    --junitxml=reports/unit.xml
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/integration/ \
	    --tb=short -q \
	    --junitxml=reports/integration.xml
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/user_stories/ \
	    -m user_story --tb=short -q \
	    --junitxml=reports/user_stories.xml
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/edge/ \
	    --tb=short -q \
	    --junitxml=reports/edge.xml
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/ \
	    --cov=src --cov=sa_utilities \
	    --cov-report=xml:reports/coverage.xml \
	    --cov-report=term \
	    --cov-fail-under=70 \
	    -q --no-header
	@echo "✓ reproduce complete"

## build: Build the Docker image
build:
	$(COMPOSE) build

## up: Start the app (detached)
up:
	$(COMPOSE) up -d

## down: Stop the app
down:
	$(COMPOSE) down

# ---------------------------------------------------------------
# Data and model download
# ---------------------------------------------------------------

## download-data: Run the SA Utilities scraping + chunking pipeline
download-data:
	$(COMPOSE) run --rm app $(PYTHON) -m sa_utilities.pipeline.runner
	$(COMPOSE) run --rm app $(PYTHON) -m sa_utilities.pipeline.embedder
	@echo "✓ data pipeline complete"

## download-models: Trigger lazy embedding model download
download-models:
	$(COMPOSE) run --rm app $(PYTHON) -c \
	    "from src.indexer.embedder import Embedder; Embedder().encode(['warmup']); print('model ready')"
	@echo "✓ models downloaded"

# ---------------------------------------------------------------
# Testing
# ---------------------------------------------------------------

## test: Run full test suite inside Docker with coverage and all JUnit reports
test:
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/unit/ \
	    --tb=short \
	    --junitxml=reports/unit.xml \
	    -q
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/integration/ \
	    --tb=short \
	    --junitxml=reports/integration.xml \
	    -q
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/user_stories/ \
	    -m user_story \
	    --tb=short \
	    --junitxml=reports/user_stories.xml \
	    -q
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/edge/ \
	    --tb=short \
	    --junitxml=reports/edge.xml \
	    -q
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/ \
	    --cov=src --cov=sa_utilities \
	    --cov-report=xml:reports/coverage.xml \
	    --cov-report=html:reports/coverage_html \
	    --cov-fail-under=70 \
	    -q --no-header
	@echo "✓ tests complete"

## test-unit: Run only unit tests
test-unit:
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/unit/ \
	    --junitxml=reports/unit.xml -q

## test-integration: Run only integration tests
test-integration:
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/integration/ \
	    --junitxml=reports/integration.xml -q

## test-stories: Run only user story acceptance tests
test-stories:
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/user_stories/ \
	    -m user_story \
	    --junitxml=reports/user_stories.xml -q

## test-edge: Run only edge case tests
test-edge:
	$(COMPOSE) run --rm app $(PYTHON) -m pytest tests/edge/ \
	    --junitxml=reports/edge.xml -q

# ---------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------

## lint: Run ruff + black + mypy
lint:
	$(COMPOSE) run --rm app $(PYTHON) -m ruff check src/ sa_utilities/ tests/
	$(COMPOSE) run --rm app $(PYTHON) -m black --check src/ sa_utilities/ tests/
	$(COMPOSE) run --rm app $(PYTHON) -m mypy src/ --ignore-missing-imports
	@echo "✓ lint clean"

## format: Auto-fix ruff + black formatting
format:
	$(COMPOSE) run --rm app $(PYTHON) -m ruff check --fix src/ sa_utilities/ tests/
	$(COMPOSE) run --rm app $(PYTHON) -m black src/ sa_utilities/ tests/

## security: Run pip-audit and save report
security:
	$(COMPOSE) exec -T app pip-audit --output /app/reports/security.txt || true
	@echo "✓ security scan saved to reports/security.txt"

# ---------------------------------------------------------------
# Load testing
# ---------------------------------------------------------------

## loadtest: Run Locust load test (requires app running via 'make up')
loadtest:
	$(COMPOSE) exec -T app locust -f tests/load/locustfile.py \
	    --headless -u 20 -r 5 \
	    --run-time 60s \
	    --host http://localhost:7860 \
	    --json > reports/benchmarks.json
	@echo "✓ load test complete — see reports/benchmarks.json"

# ---------------------------------------------------------------
# Demo
# ---------------------------------------------------------------

## demo: Run the automated demo script exercising every user story
demo:
	$(COMPOSE) run --rm app bash scripts/demo.sh

# ---------------------------------------------------------------
# Spec regeneration
# ---------------------------------------------------------------

## regenerate: Regenerate source from docs/SPEC.md via LLM (rubric Spec test)
regenerate:
	bash scripts/regenerate.sh

# ---------------------------------------------------------------
# Preflight (runs all checks the TA will run)
# ---------------------------------------------------------------

## preflight: Run every automated check locally
preflight: lint security test
	@echo ""
	@echo "✓ All preflight checks passed."

# ---------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------

## clean: Remove generated reports and Docker build cache
clean:
	rm -rf reports/*.xml reports/*.json reports/coverage_html reports/security.txt
	$(COMPOSE) down --rmi local --volumes --remove-orphans

# ---------------------------------------------------------------
# Help
# ---------------------------------------------------------------

help:
	@grep -E '^## ' Makefile | sed 's/## /  /' | column -t -s ':'
