# ⚙️ Configuration

Complete reference for configuring the Agents framework.

---

## 📁 Configuration Files

Agents uses a layered configuration system:

```
class fallback < config/defaults.toml < config/local.toml < .env / shell env < request AgentSpec
```

| File | Purpose | Committed? |
|------|---------|-----------|
| `config/defaults.toml` | Non-secret defaults | ✅ Yes |
| `config/local.toml` | Local non-secret overrides | ❌ Gitignored |
| `.env` | Secrets, tokens, deployment overrides | ❌ Gitignored |

### Override Config Paths

```bash
AGENTS_DEFAULT_CONFIG=config/defaults.toml
AGENTS_LOCAL_CONFIG=config/local.toml
```

---

## 🔑 Environment Variables

### Agent Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_PROTOCOL` | Default model protocol | `openai-chat` |
| `AGENT_MAX_TOKENS` | Max tokens per request | `4096` |
| `AGENT_MAX_RETRIES` | Retry attempts on failure | `3` |
| `AGENT_ENABLED_TOOLS` | Comma-separated tool names | `filesystem.read,filesystem.list` |
| `AGENT_BUILTIN_TOOLS` | Tools auto-registered | (see defaults) |
| `AGENT_SKILLS` | Comma-separated skill names | (none) |
| `AGENT_WORKSPACE_ROOT` | Workspace base directory | `.agents/workspaces` |
| `AGENT_WORKSPACE_LAYOUT` | Layout strategy | `auto` |
| `AGENT_SANDBOX_PROVIDER` | `local` or `docker` | `local` |
| `AGENT_RUN_STORE` | `memory`, `file`, or `sqlite` | `memory` |
| `AGENT_RUN_ROOT` | JSON file storage path | `.agents/runs` |
| `AGENT_DB_PATH` | SQLite database path | `.agents/agents.db` |
| `AGENT_CONTEXT_COMPACTION_MODEL` | Optional model for model-backed compact summaries | (none) |

### OpenAI Chat Completions

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key |
| `OPENAI_BASE_URL` | API base URL (for custom endpoints) |
| `OPENAI_MODEL` | Default model |

### OpenAI Responses API

| Variable | Description |
|----------|-------------|
| `OPENAI_RESPONSES_API_KEY` | API key |
| `OPENAI_RESPONSES_BASE_URL` | API base URL |
| `OPENAI_RESPONSES_MODEL` | Default model |

### Anthropic Claude

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key |
| `ANTHROPIC_BASE_URL` | API base URL |
| `ANTHROPIC_MODEL` | Default model |
| `AGENT_CLAUDE_API_KEY` | Project-owned override (preferred) |
| `AGENT_CLAUDE_BASE_URL` | Project-owned base URL |
| `AGENT_CLAUDE_MODEL` | Project-owned model |

### Google Gemini

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | API key |
| `GEMINI_BASE_URL` | API base URL |
| `GEMINI_MODEL` | Default model |

### MCP Servers

| Variable | Description |
|----------|-------------|
| `MCP_SERVER_NAME` | Logical name |
| `MCP_SERVER_COMMAND` | Command to launch server |
| `MCP_CLIENT_TIMEOUT` | Request timeout (seconds) |
| `MCP_EXECUTION_MODE` | `trusted` or `sandboxed` |

### Web Search

| Variable | Description |
|----------|-------------|
| `WEB_SEARCH_PROVIDER` | `tavily` (default) |
| `WEB_SEARCH_TAVILY_API_KEY` | Tavily API key |
| `WEB_SEARCH_MAX_RESULTS` | Default result count |
| `WEB_SEARCH_MAX_CREDITS_PER_RUN` | Credit limit |

### Sandbox

| Variable | Description |
|----------|-------------|
| `AGENT_SANDBOX_PROFILE` | `restricted`, `coding`, `test`, `browser` |
| `AGENT_SANDBOX_IMAGE` | Docker image (Docker provider) |
| `AGENT_SANDBOX_ALLOW_FILE_WRITE` | `true`/`false` |
| `AGENT_SANDBOX_ALLOW_PROCESS` | `true`/`false` |
| `AGENT_SANDBOX_ALLOW_NETWORK` | `true`/`false` |
| `AGENT_SANDBOX_ALLOWED_COMMANDS` | Comma-separated commands |

---

## 🤖 Model Profiles

Model profiles bundle protocol, base URL, model, and API key into a named group.

### Standard Profiles

The terminal app builds `/model` choices from these profile groups:

- `OPENAI_*`
- `OPENAI_RESPONSES_*`
- `AGENT_CLAUDE_*` (or `ANTHROPIC_*` fallback)
- `GEMINI_*`

### Custom Model Profiles

Add OpenAI-compatible endpoints (Kimi, DeepSeek, Moonshot, etc.):

```bash
# Register a profile group
AGENT_MODEL_PROFILES=kimi

# Configure the profile
AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2
AGENT_MODEL_PROFILE_KIMI_API_KEY=sk-...
AGENT_MODEL_PROFILE_KIMI_ALIASES=moonshot
```

### Multiple Custom Profiles

```bash
AGENT_MODEL_PROFILES=kimi,deepseek,custom

AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2

AGENT_MODEL_PROFILE_DEEPSEEK_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
AGENT_MODEL_PROFILE_DEEPSEEK_MODEL=deepseek-chat

AGENT_MODEL_PROFILE_CUSTOM_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_CUSTOM_BASE_URL=https://my.local.api/v1
AGENT_MODEL_PROFILE_CUSTOM_MODEL=my-model
```

### Switching Profiles

```bash
# In TUI
/model kimi

# At launch
agents tui --model-profile kimi
```

---

## 💾 Storage Backends

### Memory (Default)

In-memory storage, runs lost on restart. Best for development.

```bash
AGENT_RUN_STORE=memory
```

### File Storage

JSON files per run, durable but limited query capabilities.

```bash
AGENT_RUN_STORE=file
AGENT_RUN_ROOT=.agents/runs
```

Each run is one JSON document under `AGENT_RUN_ROOT`.

### SQLite (Recommended)

Persistent storage with rich querying. Stores:

- Run records
- Runtime events
- Checkpoints
- Trace spans
- Approval audit
- Long-term domain records

```bash
AGENT_RUN_STORE=sqlite
AGENT_DB_PATH=.agents/agents.db
```

### SQLite Domain Tables

| Table | Purpose |
|-------|---------|
| `tenants`, `users` | Identity scope |
| `agent_profiles` | Stored agent definitions (no API keys) |
| `workspace_records` | Workspace ownership and metadata |
| `artifact_records` | Run-scoped artifacts and references |
| `memory_records` | Multi-scope memories |
| `tasks`, `task_steps`, `task_attempts` | Long-running task state |
| `sandbox_leases`, `sandbox_events` | Sandbox execution tracking |
| `credential_refs` | Secret references (not raw secrets) |

---

## 📍 Workspace Layouts

### Layout Strategies

| Layout | Pattern | Use Case |
|--------|---------|----------|
| `local` | `.agents/workspaces/local/{workspace_id}` | Single-user dev |
| `scoped` | `.agents/workspaces/{tenant}/{user}/{agent}/{workspace}` | Multi-tenant |
| `auto` | Adaptive based on identity | Default |

### Configuration

```bash
AGENT_WORKSPACE_LAYOUT=auto
AGENT_WORKSPACE_ROOT=.agents/workspaces
```

### Default Identity

For local development without authentication:

```
tenant_id    default
user_id      anonymous
agent_id     default
workspace_id default
```

These trigger the compact `local` layout by default.

---

## 🔧 Sandbox Configuration

### Provider Selection

```bash
# Local (direct execution)
AGENT_SANDBOX_PROVIDER=local

# Docker (isolated container)
AGENT_SANDBOX_PROVIDER=docker
AGENT_SANDBOX_IMAGE=python:3.12-slim
```

### Profile Defaults

| Profile | Read | Write | Process | Network |
|---------|------|-------|---------|---------|
| `restricted` | ✅ | ❌ | ❌ | ❌ |
| `coding` | ✅ | ✅ | git, python3, pytest, make | ❌ |
| `test` | ✅ | ✅ | test commands | ❌ |
| `browser` | ✅ | ✅ | browser tools | ✅ |

### Manual Override

```bash
AGENT_SANDBOX_PROFILE=coding
AGENT_SANDBOX_ALLOW_FILE_WRITE=true
AGENT_SANDBOX_ALLOW_PROCESS=true
AGENT_SANDBOX_ALLOW_NETWORK=false
AGENT_SANDBOX_ALLOWED_COMMANDS=git,pytest,python3,npm
```

---

## 🔐 Permission Modes

Set via `AgentSpec` or CLI:

```python
spec = AgentSpec(
    tool_approval_mode="ask"  # auto | ask | deny
)
```

```bash
# At launch
agents tui --permission auto
agents tui --permission guarded
```

### Mode Behavior

| Mode | Behavior |
|------|----------|
| `auto` | Execute all enabled tools |
| `ask` | Pause for approval before each tool |
| `deny` | Refuse all tool calls |
| `guarded` | Read auto, confirm writes/commands |

---

## 🌐 Server Configuration

For the HTTP API server (`agents gui` or `make run`):

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVER_HOST` | Bind host | `127.0.0.1` |
| `SERVER_PORT` | Bind port | `8020` |
| `SERVER_LOG_LEVEL` | Log verbosity | `info` |
| `SERVER_CORS_ORIGINS` | Comma-separated allowed origins | (none) |
| `SERVER_STATIC_PATH` | Web UI dist path | `apps/web/dist` |

---

## 🎯 Tool Configuration

### Default Tool Set

```bash
AGENT_BUILTIN_TOOLS=filesystem.read,filesystem.list
```

### Enabled Tools

```bash
AGENT_ENABLED_TOOLS=filesystem.read,filesystem.list,patch.apply,git.status
```

### Tool-Specific Settings

```bash
# Web search
WEB_SEARCH_PROVIDER=tavily
WEB_SEARCH_TAVILY_API_KEY=tvly-...
WEB_SEARCH_MAX_RESULTS=10
WEB_SEARCH_MAX_CREDITS_PER_RUN=50

# Browser
AGENT_BROWSER_DOWNLOAD_DIR=.agents/downloads
AGENT_BROWSER_TIMEOUT=30
```

---

## 📝 Example `.env` Templates

### Minimal Local Dev

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo
AGENT_PROTOCOL=openai-chat
AGENT_RUN_STORE=memory
```

### Multi-Provider Setup

```bash
# Models
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-1.5-pro

# Custom profile
AGENT_MODEL_PROFILES=kimi
AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_API_KEY=sk-...
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2

# Persistence
AGENT_RUN_STORE=sqlite
AGENT_DB_PATH=.agents/agents.db

# Web search
WEB_SEARCH_TAVILY_API_KEY=tvly-...

# Sandbox
AGENT_SANDBOX_PROFILE=coding
```

### Production-Ready

```bash
# Models with fallback
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Persistent storage
AGENT_RUN_STORE=sqlite
AGENT_DB_PATH=/var/data/agents.db

# Docker sandbox
AGENT_SANDBOX_PROVIDER=docker
AGENT_SANDBOX_IMAGE=python:3.12-slim
AGENT_SANDBOX_PROFILE=coding

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8020
SERVER_LOG_LEVEL=info

# Workspaces
AGENT_WORKSPACE_LAYOUT=scoped
AGENT_WORKSPACE_ROOT=/var/data/workspaces
```

---

## 📚 Next Steps

- **[Quickstart](quickstart.md)** — Get running quickly
- **[Features](features.md)** — Deep dive on capabilities
- **[Architecture](architecture.md)** — System design
