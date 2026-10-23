BUN ?= $(shell command -v bun 2>/dev/null)

.PHONY: setup server host terminal-host tui web gui typecheck test test-terminal check build check-bun

check-bun:
	@test -n "$(BUN)" || (echo "bun is required; install Bun before running the TypeScript runtime." && exit 1)

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
