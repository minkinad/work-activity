PYTHON ?= python3
NPM ?= npm
SERVER_PYTHON ?= server/.venv/bin/python

.DEFAULT_GOAL := help
.PHONY: help setup setup-server setup-frontend require-server-env test test-server test-frontend lint security build build-frontend build-client check

help: ## Show available project commands
	@awk 'BEGIN {FS = ":.*## "; print "Work Activity development commands:"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: setup-server setup-frontend ## Install all development dependencies

setup-server: ## Create server/.venv and install Python dependencies
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --allow-existing --python "$(PYTHON)" server/.venv && \
		uv pip install --python "$(SERVER_PYTHON)" --requirement server/requirements-dev.txt; \
	else \
		$(PYTHON) -m venv server/.venv && \
		$(SERVER_PYTHON) -m pip install --requirement server/requirements-dev.txt; \
	fi

setup-frontend: ## Install locked frontend dependencies
	cd frontend && $(NPM) ci --ignore-scripts

require-server-env:
	@test -x "$(SERVER_PYTHON)" || { echo "Missing server/.venv. Run 'make setup-server' first." >&2; exit 1; }

test: test-server test-frontend ## Run all platform-independent tests

test-server: require-server-env ## Run server unit and API tests
	cd server && .venv/bin/python -m unittest discover -s tests -v

test-frontend: ## Run frontend unit tests
	cd frontend && $(NPM) test

lint: require-server-env ## Run Python and frontend static checks
	cd server && .venv/bin/python -m ruff check monitoring tests server.py
	cd frontend && $(NPM) run check

security: require-server-env ## Audit Python and frontend dependencies and scan server code
	cd server && .venv/bin/python -m bandit --quiet --recursive monitoring
	cd server && .venv/bin/python -m pip_audit --local --progress-spinner off --timeout 15
	cd frontend && $(NPM) audit --omit=dev

build: build-frontend ## Build artifacts supported on the current platform

build-frontend: ## Build the static dashboard into frontend/dist
	cd frontend && $(NPM) run build

build-client: ## Build the Windows client with MinGW-w64
	$(MAKE) --directory client

check: lint test security build ## Run the complete local quality gate
	cd server && .venv/bin/python -m compileall -q monitoring server.py
