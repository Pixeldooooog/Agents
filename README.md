# Agents

Agents is a TypeScript-first agent runtime with a Bun HTTP host, an Ink terminal app, and a Solid web UI.

[![TypeScript](https://img.shields.io/badge/typescript-5.x-blue.svg)](https://www.typescriptlang.org/)
[![Bun](https://img.shields.io/badge/runtime-bun-black.svg)](https://bun.sh/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Quick Start

```bash
git clone https://github.com/Pixeldooooog/Agents.git
cd Agents
bun install

# Add at least one model provider key.
cp .env.example .env

# Terminal app
bun run tui

# Web UI served by the TS host
bun run web
```

The HTTP host listens on `http://localhost:8020` by default and serves the web UI at `/ui/`.

## Project Layout

```text
apps/
  terminal/    Ink terminal interface
  web/         Solid browser UI
packages/
  host/        Bun HTTP host, static web serving, terminal host process
  core/        SDK facade, shared runtime, model profile, state, task, and tool contracts
config/        Non-secret defaults and local override shape
deploy/        Container and compose entrypoints
```

`apps/*` are product entrypoints. `packages/*` contain shared runtime/domain code. Entry files stay thin and delegate behavior into focused modules.

## Commands

```bash
bun run host          # Start the HTTP host
bun run terminal-host # Start the terminal host process
bun run tui           # Start the terminal app
bun run web           # Build web assets and serve them through the host
bun run dev-web       # Run the host plus Vite dev server
bun run typecheck     # Type-check core/host/terminal and build web
bun run test          # Run TS tests
bun run check         # Full local verification
```

The `makefile` mirrors these commands for local and container workflows:

```bash
make setup
make check
make build
make up
```

## Runtime

The host and runtime are implemented in TypeScript under `packages/host` and `packages/core`.

- `packages/core/src/config/settings.ts` loads TOML/env settings.
- `packages/core/src/sdk/agentSdkClient.ts` exposes the TS SDK client.
- `packages/core/src/models/modelProfiles.ts` builds named model profiles.
- `packages/core/src/runtime/agentRunService.ts` owns persistent run lifecycle.
- `packages/core/src/runtime/agentRuntime.ts` runs model turns and emits protocol-neutral events.
- `packages/core/src/store/jsonStateStore.ts` persists runs and tasks to JSON state.
- `packages/host/src/api/agentRoutes.ts` exposes the HTTP API.
- `packages/host/src/terminal/main.ts` exposes the terminal host process.

## Model Configuration

Add provider keys in `.env` or shell environment:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o

AGENT_CLAUDE_API_KEY=...
AGENT_CLAUDE_MODEL=claude-opus-4-7

GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-pro
```

Custom OpenAI-compatible profiles use named groups:

```bash
AGENT_MODEL_PROFILES=kimi
AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2
AGENT_MODEL_PROFILE_KIMI_API_KEY=...
```

Switch profiles in the terminal with `/model`.

## HTTP API

```bash
curl -fsS http://127.0.0.1:8020/health

curl -fsS http://127.0.0.1:8020/api/v1/agent/model-profiles

curl -X POST http://127.0.0.1:8020/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","model_profile":"openai"}'
```

## Documentation

- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Module Map](docs/module-map.md)
- [Features](docs/features.md)
