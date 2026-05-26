IMAGE ?= agents
TAG ?= latest
PORT ?= 8020
VENV ?= .venv
PYTHON_BIN ?= $(shell command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3.10 2>/dev/null)
UV ?= $(shell command -v uv 2>/dev/null)
BUN ?= $(shell command -v bun 2>/dev/null)
HOST_PIP ?= $(shell command -v pip3 2>/dev/null || command -v pip 2>/dev/null)
PYTHON ?= $(VENV)/bin/python
PIP ?= $(PYTHON) -m pip
PYTHONDONTWRITEBYTECODE ?= 1

export PYTHONDONTWRITEBYTECODE

.PHONY: check-python venv setup setup-tui setup-terminal run tui web gui terminal terminal-fixture terminal-fixture-fullscreen terminal-manual-smoke manual-smoke terminal-audit terminal-audit-complete cli bridge-fallback dev-web stop test test-terminal check doctor package build-web build up down log

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
	@if [ -n "$(BUN)" ]; then cd apps/terminal && $(BUN) install; else echo "bun is required for the TUI. Install bun or run make bridge-fallback."; fi

setup-tui:
	@test -n "$(BUN)" || (echo "bun is required for the TUI." && exit 1)
	cd apps/terminal && $(BUN) install

setup-terminal: setup-tui

run: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.server

tui: venv
	@test -n "$(BUN)" || (echo "bun is required for make tui. Use make bridge-fallback for the Python debug fallback." && exit 1)
	@cd apps/terminal && PYTHONPATH=$(CURDIR)/src $(BUN) run src/main.tsx --repo-root ../.. --python $(PYTHON) $(ARGS)

web: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.entrypoints.agents gui

gui: web

terminal: tui

terminal-fixture: venv
	@test -n "$(BUN)" || (echo "bun is required for make terminal-fixture." && exit 1)
	@cd apps/terminal && $(BUN) run fixture

terminal-fixture-fullscreen: venv
	@test -n "$(BUN)" || (echo "bun is required for make terminal-fixture-fullscreen." && exit 1)
	@cd apps/terminal && AGENTS_TERMINAL_FULLSCREEN=1 $(BUN) run fixture

terminal-manual-smoke:
	@test -n "$(BUN)" || (echo "bun is required for make terminal-manual-smoke." && exit 1)
	@cd apps/terminal && $(BUN) run manual-smoke:record

manual-smoke: terminal-manual-smoke

terminal-audit:
	@test -n "$(BUN)" || (echo "bun is required for make terminal-audit." && exit 1)
	@cd apps/terminal && $(BUN) run tui-audit

terminal-audit-complete:
	@test -n "$(BUN)" || (echo "bun is required for make terminal-audit-complete." && exit 1)
	@cd apps/terminal && $(BUN) run tui-audit:complete

bridge-fallback: venv
	@PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.bridge.fallback.main chat

cli: tui

dev-web: venv
	@echo "Starting backend..."
	@PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.interfaces.server & BACKEND_PID=$$!; \
	trap "kill $$BACKEND_PID 2>/dev/null" EXIT; \
	cd apps/web && npm run dev

stop:
	-pkill -f "agents.interfaces.server.app:app" 2>/dev/null || true

test: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests -q

test-terminal:
	@test -n "$(BUN)" || (echo "bun is required for terminal tests." && exit 1)
	cd apps/terminal && $(BUN) run typecheck && $(BUN) run render-smoke && $(BUN) run interaction-smoke && $(BUN) run app-smoke && $(BUN) run app-compact-smoke && $(BUN) run app-short-smoke && $(BUN) run app-narrow-smoke && $(BUN) run app-tiny-smoke && $(BUN) run app-tiny-fullscreen-smoke && $(BUN) run app-flow-smoke && $(BUN) run app-compact-flow-smoke && $(BUN) run app-short-fullscreen-flow-smoke && $(BUN) run app-fullscreen-smoke && $(BUN) run app-compact-fullscreen-smoke && $(BUN) run app-inline-smoke && $(BUN) run app-pending-resume-smoke

check: test test-terminal

doctor: venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m agents.entrypoints.doctor

package: venv
	$(PIP) install --upgrade build twine
	rm -rf dist build
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

build-web:
	cd apps/web && npm run build

build:
	docker build -f deploy/Dockerfile -t $(IMAGE):$(TAG) .

up:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml up -d

down:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml down

log:
	IMAGE=$(IMAGE) TAG=$(TAG) PORT=$(PORT) docker compose -f deploy/docker-compose.yml logs -f --tail 200
