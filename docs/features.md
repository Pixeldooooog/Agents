# Features

## TypeScript Runtime

- Bun HTTP host.
- NDJSON terminal host.
- Shared core runtime package.
- JSON state store for runs and tasks.
- Protocol-neutral runtime events.

## Model Profiles

The runtime supports named profiles for:

| Profile | Protocol |
|---|---|
| `openai` | OpenAI Chat Completions |
| `responses` | OpenAI Responses |
| `claude` | Claude Messages |
| `gemini` | Gemini Generate Content |
| custom names | OpenAI-compatible endpoints |

Switch profiles from the terminal with `/model`.

## Terminal UI

- Ink-based local interface.
- Slash command catalog.
- Session list and resume.
- Runtime status panels.
- Permission and prompt inspection.
- Fixture and flow smoke coverage.

## Web UI

- Solid/Vite frontend.
- Served by the TS host at `/ui/`.
- Uses the same HTTP API as external clients.

## Tool Surface

The current TS runtime exposes a compact built-in tool set:

| Tool | Purpose |
|---|---|
| `filesystem.read` | Read workspace files |
| `filesystem.list` | List workspace directories |

The tool registry lives in `packages/core/src/tools/toolRegistry.ts`, while individual tool domains live under `packages/core/src/tools/` or their matching domain directory.

## State

`packages/core/src/store/jsonStateStore.ts` persists:

- Runs
- Runtime events
- Tasks
- Terminal session-facing state

The default state path is `.kevin/host/state.json`.
