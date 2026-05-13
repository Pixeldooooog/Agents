# ✨ Features

A deep dive into the core capabilities of Agents.

---

## 🤖 Multi-Model Protocol Layer

Agents abstracts away the differences between model providers, giving you a unified interface for streaming, tool calling, and reasoning.

### Supported Providers

| Provider | Protocol | Model Examples |
|----------|----------|----------------|
| OpenAI | `openai-chat` | `gpt-4-turbo`, `gpt-4o`, `gpt-3.5-turbo` |
| OpenAI | `openai-responses` | `o1-preview`, `o1-mini` |
| Anthropic | `claude-messages` | `claude-3-5-sonnet`, `claude-3-opus` |
| Google | `gemini` | `gemini-1.5-pro`, `gemini-1.5-flash` |
| Custom | `openai-chat` | Kimi, DeepSeek, any OpenAI-compatible API |

### Switching Models

```python
# In Python
spec = AgentSpec(model="claude-3-5-sonnet")

# In TUI
/model claude-3-5-sonnet

# Via CLI flag
agents tui --model-profile claude
```

### Streaming Events

All providers emit protocol-neutral events:

```python
async for event in client.stream(messages):
    match event.type:
        case "text_delta":
            print(event.delta, end="")
        case "reasoning_delta":
            print(f"[Thinking: {event.delta}]")
        case "tool_call_delta":
            print(f"\n→ Calling {event.tool_name}")
        case "usage":
            print(f"Tokens: {event.input_tokens}/{event.output_tokens}")
```

---

## 🛠️ Tool System

Built-in tools cover the most common agent needs, all guarded by sandbox and permission policies.

### Tool Catalog

| Tool | Risk | Description |
|------|------|-------------|
| `filesystem.read` | 🟢 Low | Read workspace files |
| `filesystem.list` | 🟢 Low | List workspace files |
| `search.grep` | 🟢 Low | Regex search over text files |
| `git.status` | 🟢 Low | Git working tree status |
| `git.diff` | 🟢 Low | Git diff (truncated) |
| `git.log` | 🟢 Low | Git history |
| `test.discover` | 🟢 Low | Suggest test commands |
| `filesystem.write` | 🟡 Medium | Write/create files |
| `filesystem.delete` | 🟡 Medium | Delete files |
| `filesystem.move` | 🟡 Medium | Move/rename files |
| `patch.apply` | 🟡 Medium | Apply structured patches |
| `web.search` | 🟡 Medium | Tavily-backed web search |
| `web.extract` | 🟡 Medium | Extract content from URLs |
| `web.map` | 🔴 High | Discover site URLs |
| `git.add`, `git.commit` | 🔴 High | Git mutations |
| `test.run` | 🔴 High | Run test commands |
| `browser.open` | 🔴 High | Browser navigation |
| `browser.download` | 🔴 High | Browser downloads |
| `shell.run` | 🔴 High | Arbitrary shell commands |

### Enabling Tools

```python
spec = AgentSpec(
    model="gpt-4",
    tools=[
        "filesystem.read",
        "filesystem.list",
        "patch.apply",
        "git.status",
    ]
)
```

### Tool Permissions

Restrict what tools can do:

```python
spec = AgentSpec(
    tools=["filesystem.write", "shell.run"],
    tool_permissions={
        "filesystem.write": {
            "paths": ["./src/*", "./tests/*"]
        },
        "shell.run": {
            "commands": ["git", "npm", "pytest"],
            "deny_commands": ["rm", "sudo"]
        }
    }
)
```

### MCP Integration

Extend with custom tools via Model Context Protocol:

```python
from agents.kernel.capabilities.tools import load_mcp_server

# Load a stdio MCP server
await load_mcp_server("path/to/mcp_server.py")

# Or via configuration
spec = AgentSpec(
    mcp_servers=["my_tools", "database_tools"]
)
```

Configure MCP servers in `.env`:

```bash
MCP_SERVER_NAME=my_tools
MCP_SERVER_COMMAND=python /path/to/server.py
MCP_CLIENT_TIMEOUT=30
MCP_EXECUTION_MODE=trusted
```

---

## ✋ Approval Workflows

Human-in-the-loop control for sensitive operations.

### Approval Modes

| Mode | Behavior |
|------|----------|
| `auto` | Execute allowed tools without pausing |
| `ask` | Pause and prompt before each tool call |
| `deny` | Return denied tool results without executing |

### Configuration

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["filesystem.write", "shell.run"],
    tool_approval_mode="ask",
)
```

### Approval Flow

1. Agent decides to call a tool
2. Runtime emits `tool_approval_required` event
3. Run status changes to `awaiting_approval`
4. Checkpoint is created with pending tool calls
5. User approves or denies via TUI/Web UI
6. Runtime resumes execution

### Resume via API

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/runs/run_xxx/approval \
  -H 'Content-Type: application/json' \
  -d '{
    "tool_call_ids": ["call_abc"],
    "approved": true
  }'
```

### Approval Audit

Every approval decision is recorded with:
- Tool name and arguments
- Risk level
- Affected paths/commands
- Network domains
- Cost estimates
- Patch previews
- User decision and timestamp

Audit records persist independently of trace spans.

---

## 🔒 Sandbox & Workspace Model

The agent runtime stays in the control plane. The sandbox is the execution plane for high-risk native tools.

### Execution Flow

```
model → runtime → tool registry → builtin tool → SandboxClient → execution → workspace
```

### Sandbox Providers

| Provider | Use Case |
|----------|----------|
| `local` | Direct execution in workspace path |
| `docker` | Isolated container with workspace mounted at `/workspace` |

### Sandbox Profiles

| Profile | Default Behavior |
|---------|-----------------|
| `restricted` | Read-only workspace access |
| `coding` | File write + allowlisted commands (git, python3, pytest, make) |
| `test` | Process execution for test commands |
| `browser` | Browser-oriented process and network access |

### Configuration

```bash
AGENT_SANDBOX_PROFILE=coding
AGENT_SANDBOX_PROVIDER=docker
AGENT_SANDBOX_IMAGE=python:3.12-slim
AGENT_SANDBOX_ALLOW_FILE_WRITE=true
AGENT_SANDBOX_ALLOW_PROCESS=true
AGENT_SANDBOX_ALLOWED_COMMANDS=git,pytest,python3
```

### Workspace Isolation

Each agent runs in an isolated workspace identified by:

```
tenant_id / user_id / agent_id / workspace_id
```

### Workspace Layouts

| Layout | Path Pattern | When Used |
|--------|--------------|-----------|
| `local` | `.agents/workspaces/local/default` | Dev/terminal |
| `local named` | `.agents/workspaces/local/{workspace_id}` | Multiple local projects |
| `scoped` | `.agents/workspaces/{tenant}/{user}/{agent}/{workspace}` | Multi-tenant |
| `auto` (default) | Compact local for placeholder identities, scoped otherwise | Adaptive |

---

## 🧠 Memory & Context Management

Long-running conversations with intelligent context handling.

### Layered Context

The context system assembles fragments in order:

```
1. System prompt
2. Runtime policy
3. Workspace instructions
4. Skills
5. Memory (retrieved)
6. Tool hints
7. Task context
8. Conversation history
```

### Memory Types

| Scope | Purpose |
|-------|---------|
| User | Personal preferences across sessions |
| Agent | Agent-specific knowledge |
| Workspace | Project-level facts |
| Run | Single-run notes |

### Enabling Memory

```python
spec = AgentSpec(
    model="gpt-4",
    memory_enabled=True,
    memory_profile="research_assistant",
)
```

### Context Compaction

When approaching token limits, the system automatically:

1. Identifies oldest non-essential messages
2. Generates a deterministic summary
3. Replaces the messages with the summary
4. Preserves tool calls and recent context

```python
spec = AgentSpec(
    context_window_tokens=128000,
    compaction_strategy="deterministic",
)
```

---

## ⚡ Streaming & Observability

Real-time visibility into agent execution.

### Event Stream

```python
async for event in runtime.stream(prompt):
    print(event.type, event.payload)
```

Common events:
- `run_created` — Run started
- `text_delta` — Streaming text
- `reasoning_delta` — Streaming reasoning
- `tool_call_start` — Tool invocation begins
- `tool_call_result` — Tool returns
- `tool_approval_required` — Awaiting approval
- `usage` — Token consumption
- `error` — Execution error
- `done` — Run completed

### Trace Spans

Every run generates ordered trace spans:

```bash
curl http://127.0.0.1:8020/api/v1/agent/runs/run_xxx/trace
```

Returns:
- Run-level spans
- Model call spans
- Tool execution spans
- Approval spans
- Sandbox events

### Persistence

Choose your storage backend:

```bash
# In-memory (default, dev only)
AGENT_RUN_STORE=memory

# Local JSON files
AGENT_RUN_STORE=file
AGENT_RUN_ROOT=.agents/runs

# SQLite (recommended for production)
AGENT_RUN_STORE=sqlite
AGENT_DB_PATH=.agents/agents.db
```

---

## 📋 Long-Running Tasks

Foundation for background execution.

### Task Model

```
Task → Steps → Attempts
```

Each task has:
- Status (pending, running, completed, failed)
- Backing run_id
- Step lifecycle
- Retry attempts on failure

### Through API

```bash
# Create task
curl -X POST http://127.0.0.1:8020/api/v1/agent/tasks \
  -d '{"title":"Daily report","message":"Generate today's metrics report"}'

# Run it
curl -X POST http://127.0.0.1:8020/api/v1/agent/tasks/task_xxx/run

# Check status
curl http://127.0.0.1:8020/api/v1/agent/tasks/task_xxx
```

---

## 🎨 Skills

Reusable agent capabilities packaged as skills.

### Built-in Skills

- `data_analysis` — Tabular data processing
- `code_review` — Code quality assessment
- `documentation` — Technical writing
- More in `agents.kernel.capabilities.skills`

### Custom Skills

```python
spec = AgentSpec(
    skills=["data_analysis", "my_custom_skill"]
)
```

Skills are layered into the system prompt and provide tool hints, examples, and constraints.

---

## 🔐 Security Features

### Secret Redaction

API keys and tokens are automatically redacted from:
- Log messages
- Error reports
- Trace spans
- Audit records

### Credential Isolation

```python
# Credentials never enter the sandbox
# API calls happen in the control plane
```

### Pluggable Payload Protection

```python
from agents.kernel.governance import register_payload_protector

register_payload_protector(my_pii_redactor)
```

---

## 🧩 Multi-Agent Foundations

Primitives for orchestration (in development):

- **Roles** — Planner, worker, reviewer
- **Routers** — Direct messages between agents
- **Workflows** — DAG-based task orchestration

```python
# Coming soon
from agents.kernel.orchestration import MultiAgentSession

session = MultiAgentSession(
    agents={
        "planner": planner_spec,
        "worker": worker_spec,
        "reviewer": reviewer_spec,
    },
    workflow=workflow_dag,
)
```

---

## 📚 Next Steps

- **[Configuration](configuration.md)** — All env vars and settings
- **[Use Cases](use-cases.md)** — See features in action
- **[Architecture](architecture.md)** — How it all fits together
