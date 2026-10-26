# Kevin Quickstart

## Requirements

- Bun 1.4.4 and Git
- macOS or Linux for local command execution
- At least one model provider key
- Docker only if you build or run the container image

## Install

```bash
bun install
cp .env.example .env
```

Add a provider key:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=your-model-id
```

## Run The Terminal

```bash
bun run tui
```

Useful slash commands:

| Command | Purpose |
|---|---|
| `/status` | Show runtime state |
| `/model` | List or switch model profiles |
| `/sessions` | List saved terminal sessions |
| `/resume <id>` | Resume a saved terminal session |
| `/tasks` | List task records |
| `/permissions` | Show permission state |
| `/prompt` | Inspect prompt context |
| `/diff` | Show workspace diff |

## Run The Web UI

```bash
bun run web
```

Open `http://localhost:8020/ui/`.

For local frontend iteration, explicitly configure the Host browser origins in `.env`:

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Then run:

```bash
bun run dev-web
```

## Call The HTTP API

```bash
bun run host
```

```bash
curl -fsS http://127.0.0.1:8020/health
curl -fsS http://127.0.0.1:8020/api/v1/agent/model-profiles
```

Chat request:

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Summarize this repository","model_profile":"openai"}'
```

Streaming request:

```bash
curl -N -X POST http://127.0.0.1:8020/api/v1/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Summarize this repository","model_profile":"openai"}'
```

## Verify

```bash
bun run typecheck
bun run test
bun run --cwd apps/terminal app-flow-smoke
```
