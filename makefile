IMAGE ?= agents
TAG ?= latest
PORT ?= 8010
VENV ?= .venv
PYTHON_BIN ?= $(shell command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null)
UV ?= $(shell command -v uv 2>/dev/null)
BUN ?= $(shell command -v bun 2>/dev/null)
HOST_PIP ?= $(shell command -v pip3 2>/dev/null || command -v pip 2>/dev/null)
PYTHON ?= $(VENV)/bin/python
PIP ?= $(PYTHON) -m pip

.PHONY: check-python venv setup setup-terminal run terminal cli bridge-fallback dev-web stop test smoke build up down log

check-python:
	@test -n "$(PYTHON_BIN)" || (echo "Python 3.10+ is required." && exit 1)
	@$(PYTHON_BIN) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'

venv: check-python
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "Creating $(VENV) with $(PYTHON_BIN)"; \
		if [ -n "$(UV)" ]; then $(UV) venv --seed --python "$(PYTHON_BIN)" "$(VENV)"; \
		else $(PYTHON_BIN) -m venv "$(VENV)"; fi; \
	fi
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
	@if ! $(PYTHON) -m pip --version >/dev/null 2>&1; then \
		echo "Bootstrapping pip in $(VENV)"; \
		if $(PYTHON) -m ensurepip --upgrade >/dev/null 2>&1; then :; \
		elif [ -n "$(UV)" ]; then $(UV) pip install --python "$(PYTHON)" pip setuptools wheel; \
		elif [ -n "$(HOST_PIP)" ]; then "$(HOST_PIP)" --python "$(PYTHON)" install pip setuptools wheel; \
		else echo "pip is unavailable; install pip3 or uv, then rerun make setup."; exit 1; fi; \
	fi
	@$(PYTHON) -m pip --version >/dev/null

setup: venv
	$(PIP) install -e ".[test]"
	@if [ -f apps/web/package-lock.json ]; then cd apps/web && npm ci; else cd apps/web && npm install; fi
	@if [ -n "$(BUN)" ]; then cd apps/terminal && $(BUN) install; else echo "bun is required for the terminal app. Install bun or run make bridge-fallback."; fi

setup-terminal:
	@test -n "$(BUN)" || (echo "bun is required for the terminal app." && exit 1)
	cd apps/terminal && $(BUN) install

run: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.server

terminal: venv
	@test -n "$(BUN)" || (echo "bun is required for make terminal. Use make bridge-fallback for the Python debug fallback." && exit 1)
	@cd apps/terminal && PYTHONPATH=$(CURDIR)/src $(BUN) run src/main.tsx --repo-root ../.. --python $(PYTHON) $(ARGS)

cli: terminal

bridge-fallback: venv
	@PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.bridge.fallback.main chat

dev-web: venv
	@echo "Starting backend..."
	@PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.server & BACKEND_PID=$$!; \
	trap "kill $$BACKEND_PID 2>/dev/null" EXIT; \
	cd apps/web && npm run dev

stop:
	-pkill -f "agents.interfaces.server.app:app" 2>/dev/null || true

test: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests -q

smoke: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.entrypoints.smoke
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/test_delivery_smoke.py tests/test_agent_api.py::test_agent_run_trace_api_returns_spans -q
	@test -n "$(BUN)" || (echo "bun is required for terminal typecheck. Run make setup-terminal first." && exit 1)
	cd apps/terminal && $(BUN) run typecheck
	cd apps/web && npm run build

build:
	docker build -f deploy/Dockerfile -t $(IMAGE):$(TAG) .

up:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml up -d

down:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml down

log:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml logs -f --tail 200
