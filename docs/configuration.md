# Configuration

Configuration is loaded by `packages/core/src/config/settings.ts`.

## Files

```text
config/defaults.toml < config/local.toml < .env / shell env
```

| File | Purpose | Committed |
|---|---|---|
| `config/defaults.toml` | Non-secret project defaults | yes |
| `config/local.toml` | Local non-secret overrides | no |
| `.env` | Secrets and deployment overrides | no |

## Host

| Variable | Purpose | Default |
|---|---|---|
| `HOST` | Bind host | `127.0.0.1` |
| `PORT` | Bind port | `8020` |
| `CORS_ORIGINS` | Explicit comma-separated browser origins | empty (same origin only) |
| `ACCESS_TOKEN` | Bearer token; required for non-loopback binding | empty on loopback |
| `AGENT_MAX_TOOL_ITERATIONS` | Operator tool-loop ceiling; request hints can only reduce it | `40` |
| `AGENT_STATE_PATH` | JSON state file | `.agents/host/state.json` |

## Agent Runtime

| Variable | Purpose |
|---|---|
| `AGENT_PROTOCOL` | Default protocol |
| `AGENT_MAX_TOKENS` | Max model output tokens |
| `AGENT_MAX_RETRIES` | Retry attempts |
| `AGENT_BUILTIN_TOOLS` | Built-in tool list |
| `AGENT_ENABLED_TOOLS` | Enabled tool override |
| `AGENT_WORKSPACE_ROOT` | Workspace root |
| `AGENT_RUN_STORE` | Runtime store mode |
| `AGENT_RUN_ROOT` | Run artifact root |
| `AGENT_CONTEXT_COMPACTION_MODEL` | Optional compaction model |

## Model Providers

OpenAI Chat:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

OpenAI Responses:

```bash
OPENAI_RESPONSES_API_KEY=...
OPENAI_RESPONSES_BASE_URL=https://api.openai.com/v1
OPENAI_RESPONSES_MODEL=o3
```

Claude:

```bash
AGENT_CLAUDE_API_KEY=...
AGENT_CLAUDE_BASE_URL=https://api.anthropic.com
AGENT_CLAUDE_MODEL=claude-opus-4-7
```

Gemini:

```bash
GEMINI_API_KEY=...
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1
GEMINI_MODEL=gemini-2.5-pro
```

## Custom Profiles

```bash
AGENT_MODEL_PROFILES=kimi,deepseek

AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2
AGENT_MODEL_PROFILE_KIMI_API_KEY=...
AGENT_MODEL_PROFILE_KIMI_ALIASES=moonshot
```

Terminal users can switch with `/model kimi`.

## Execution isolation status

Shell tools currently execute on the host. Configuration names do not establish a container or filesystem security boundary. The macOS feasibility script in `scripts/baseline/` is not integrated into tool execution; Linux and production isolation remain pending.

## Local development and remote binding

Use Bun 1.4.4 (`.bun-version`). For the Vite development UI, explicitly set `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173` in the Host environment or `.env`; production defaults remain same-origin. Wildcard origins are rejected. The current settings loader lets `.env` override shell variables.

`HOST=0.0.0.0` requires a nonempty `ACCESS_TOKEN`; clients send `Authorization: Bearer <token>`. Docker Compose requires that variable and publishes only to the host loopback interface. Health and static UI remain public; API operations require the configured token. Loopback without a token is a limited local mode, not protection against other local processes. Automatic local token provisioning is pending.

A zero, negative or invalid tool iteration setting falls back to 40. Request limits cannot increase the operator ceiling. This is a tool-loop bound, not a persisted token/cost/time budget.

## Local command and tool boundaries

The current LocalExecutor is host execution, with no Docker requirement and no filesystem/network isolation. Native sandbox rollout is deferred; requests requiring isolated execution fail closed. See `docs/baseline/adr-001-local-execution.md`.

- Shell foreground/background: 30-second default, 120-second ceiling; stdout and stderr each retain at most 128 KiB, with byte counts and truncation flags.
- POSIX cancellation: TERM then KILL for the process group. Runtime/SDK cancellation is forwarded to executing commands. This does not implement durable Task cancellation or contain processes that escape the group.
- Background records: at most 128 transient entries; finished entries may be evicted. No output file path is advertised because outputs are held in memory.
- All 120 built-in tools declare input schemas. Invalid types are rejected without coercion before invoking handlers. Input and serialized tool result limits are 256 KiB each; oversized successful results remain successful and carry a JSON truncation preview.
- Enabled/denied tool rules apply at runtime dispatch and approval resume. Explicit approval requirements also apply in auto mode. Persistent scope-bound grants and action reconciliation remain B2 work.
