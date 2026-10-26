BUN ?= $(shell command -v bun 2>/dev/null)
BUN_VERSION := $(shell cat .bun-version 2>/dev/null)

# package.json scripts invoke `bun` again; put the selected Bun first on PATH so nested runs use the same version.
ifneq ($(findstring /,$(BUN)),)
export PATH := $(abspath $(dir $(BUN))):$(PATH)
endif

.PHONY: setup server host terminal-host tui web gui typecheck test test-terminal check build check-bun

check-bun:
	@test -n "$(BUN)" || (echo "bun is required; install Bun $(BUN_VERSION) before running the TypeScript runtime." >&2 && exit 1)
	@test -n "$(BUN_VERSION)" || (echo ".bun-version is missing or empty." >&2 && exit 1)
	@actual="$$("$(BUN)" --version)"; \
	if [ "$$actual" != "$(BUN_VERSION)" ]; then \
		echo "Bun $(BUN_VERSION) is required (.bun-version), but $(BUN) is $$actual." >&2; \
		echo "Install Bun $(BUN_VERSION), or run with BUN=/path/to/bun-$(BUN_VERSION)." >&2; \
		exit 1; \
	fi

setup: check-bun
	@$(BUN) install

server: check-bun
	@$(BUN) run packages/host/src/main.ts

host: server

terminal-host: check-bun
	@$(BUN) run packages/host/src/terminal/main.ts

tui: check-bun
	@$(BUN) run --cwd apps/terminal src/main.tsx --repo-root ../..

web: check-bun
	@$(BUN) run build-web
	@$(BUN) run packages/host/src/main.ts

gui: web

typecheck: check-bun
	@$(BUN) run typecheck

test: check-bun
	@$(BUN) run test

test-terminal: check-bun
	@$(BUN) run test-terminal

check: check-bun
	@$(BUN) run check

build: typecheck
