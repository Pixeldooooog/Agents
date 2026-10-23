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
| `HOST` | Bind host | `0.0.0.0` |
| `PORT` | Bind port | `8020` |
| `CORS_ORIGINS` | Comma-separated CORS origins | `*` |
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

## Sandbox Defaults

The TS defaults use a Node-oriented image for container execution:

```toml
sandbox_image = "node:22-alpine"
sandbox_allowed_commands = "git,node,npm,bun,make"
```
