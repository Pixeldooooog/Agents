# Agents

Agents is a Python-first agent system organized as a reusable kernel, a shared platform/control layer, and product interfaces.

The project boundary is intentionally strict:

```text
apps/web      -> agents.interfaces.server -> agents.platform -> agents.kernel
apps/terminal -> agents.interfaces.bridge -> agents.platform -> agents.kernel

agents.interfaces.* -> agents.platform -> agents.kernel
agents.kernel       -> no platform, interface, FastAPI, bridge, or UI dependency
```

`src/agents/kernel/` is the core SDK/kernel. It defines agent specs, model protocols, context assembly, capabilities, governance, runtime loops, checkpoints, run records, workspaces, skills, memory, and MCP integration.

`src/agents/platform/` is the shared control plane. It owns run/session lifecycle services, store composition, terminal profiles, and command metadata that must be reused by both local and hosted interfaces.

`src/agents/interfaces/server/` is the HTTP/SSE adapter. `src/agents/interfaces/bridge/` is the local NDJSON adapter used by the terminal product. `apps/terminal/` and `apps/web/` are UI products and do not import Python kernel internals.

## Technical Documentation

- [Architecture](docs/architecture.md): top-level package boundaries and request flow.
- [Technical design](docs/technical-design.md): control/data/execution plane, sandbox reasoning, and the code-snippet executor tradeoff.
- [Module map](docs/module-map.md): module-by-module responsibilities, rationale, and extension points.
- [TODO plan](docs/roadmap.md): staged roadmap toward a complete long-running agent system.
- [Module notes](docs/modules/README.md): focused notes for sandbox, runtime, and tools.

## Current Capabilities

- Multi-protocol model layer: OpenAI Chat Completions, OpenAI Responses, Claude Messages, Gemini.
- Protocol-neutral streaming events for text deltas, reasoning deltas, tool call deltas, usage, and final messages.
- Agent runtime with tool-call loop, streaming, hook points, checkpoint/resume support, and max-iteration guard.
- Context system with layered fragments: system, runtime policy, workspace instructions, skills, memory, tool hints, task context.
- Tool registry with concurrent execution, timeout handling, tool metadata, error-to-tool-result conversion, and MCP stdio loading.
- Pluggable sandbox execution layer with local and Docker providers; native tools execute through `SandboxClient` against a persistent workspace.
- `AgentSpec` spec layer for model overrides, enabled tools, skills, workspace scope, tool permissions, memory profile, and metadata.
- Tool approval flow with `auto`, `ask`, and `deny` modes, checkpoint-backed pause/resume, run status `awaiting_approval`, and web Approve/Deny controls.
- Long-running task foundation with task, step, attempt records and memory/SQLite stores.
- Task queue/worker primitives for background execution over the same task runner.
- Workspace-scoped builtin tools for file read/list/write, structured patching, text search, web search/extract/map, git status/diff, test commands, browser fetch/download, and shell fallback, guarded by sandbox and permission policy.
- Memory retrieval and deterministic context compaction integrated into session assembly/windowing for long-context runs.
- Multi-agent role/router and workflow DAG primitives for future planner/worker/reviewer orchestration.
- Governance security primitives for secret redaction and pluggable payload protection providers.
- Workspace isolation through `tenant_id / user_id / agent_id / workspace_id`, with a compact local filesystem layout for dev and terminal usage.
- Run tracking through `RunStore`, backed by memory, local JSON files, or SQLite.
- SQLite persistence for run records, runtime events, checkpoints, approval audit, and trace spans.
- Long-term data stores for tenants/users, agent profiles, workspace records, memories, sandbox leases, and credential references.
- Traceable run timelines through `agents.kernel.governance.tracing`, with separate approval audit records through `agents.kernel.governance.audit`.
- Server chat APIs return `run_id`; streaming emits a `run_created` event before model/tool events.
- Web UI can refresh the active run trace and display spans, approval records, sandbox events, and run artifacts.
- Terminal coding profile runs on the agent kernel through a local NDJSON bridge, binds a local workspace, enables read/write/patch/search/git/test/shell tools, and keeps terminal UI concerns outside `agents.kernel`.

## Repository Layout

```text
src/
  agents/
    kernel/
      assembly/       Build AgentSession from settings + AgentSpec
      capabilities/   Tools, skills, MCP loading, and memory capability APIs
        sandbox/      Local/Docker sandbox clients and sandbox lease records
      config/         Shared runtime settings, config loader, and model profile resolution
      context/        ContextPack, ContextBuilder, windowing, request compilation
      governance/     Permissions, credentials, audit, tracing
      hooks/          Runtime hooks and hook composition
      models/         ModelClient, adapters, protocol, transports, retry, errors
      orchestration/  Future multi-agent planner/router/supervisor boundary
      persistence/    Shared local persistence primitives
      runtime/        Agent loop, session, state, events, turns, checkpoints
      specs/          AgentSpec, model/workspace/permission specs
      state/          Runs, identity, agent profiles, workspace records
      tasks/          Long-running task, step, and attempt state machine
      workflows/      Future workflow/DAG boundary
      schema.py       Core message/tool/model/runtime data types

    platform/
      commands.py     Shared slash command metadata
      persistence.py  Store composition for runs, checkpoints, traces, tasks, memory
      profiles.py     Local profile/tool/permission defaults
      sessions/       Run lifecycle service and store factories

    interfaces/
      server/
        api/          FastAPI routes and HTTP schemas
        auth/         Future auth boundary
        core/         Server settings, logging, middleware, exceptions
        streaming/    Future SSE/WebSocket protocol helpers
        static.py     Mounts apps/web/dist at /ui
      bridge/         Internal NDJSON bridge for the terminal app

    entrypoints/      Console entrypoints

apps/
  terminal/       TypeScript Ink terminal interface
  web/            SolidJS + Vite browser interface
tests/            Unit and boundary tests
docs/             Architecture notes
```

## Quick Start

```bash
make setup
cp .env.example .env
```

Edit `.env` and configure at least one model protocol API key and model. `make setup` installs Python dependencies, the web frontend dependencies, and the terminal app dependencies when `bun` is available.

Start the server:

```bash
make run
curl http://127.0.0.1:8010/health
```

Start the terminal chat:

```bash
make terminal
```

`make terminal` starts the TypeScript Ink terminal frontend. It launches the Python bridge locally, binds the current directory as the workspace, enables coding tools, and asks before write/execute tools. The Python fallback remains only as a bridge/debug path:

```bash
make bridge-fallback
```

For a different workspace:

```bash
make terminal ARGS="--workspace-path ./sandbox-game"
```

Useful terminal switches are forwarded to the Python bridge:

```bash
make terminal ARGS="--profile chat"                  # read-oriented chat profile
make terminal ARGS="--profile coding"                # local coding profile, default
make terminal ARGS="--profile browser"               # coding tools plus browser/web tools
make terminal ARGS="--permission auto"               # run enabled tools without approval prompts
make terminal ARGS="--permission guarded"            # read automatically, confirm writes/commands
make terminal ARGS="--tools filesystem.read,patch.apply,test.run"
```

Inside the terminal chat:

```text
/help       show terminal commands
/status     show protocol, workspace, permission, token estimate
/model      show configured model profiles and switch with /model <profile>
/models     alias for /model
/doctor     check local model, workspace, and tool readiness
/workspace  show workspace path and logical scope
/tools      show enabled tools
/context    show context window usage
/trace      show context assembly trace
/fold       collapse long thinking/assistant/tool blocks
/unfold     expand long thinking/assistant/tool blocks
/queue      show queued messages
/cancel     clear queued messages
/clear      reset conversation messages
/exit       leave the chat
```

Terminal shortcuts:

```text
up/down    browse input history, or move inside an active picker/suggestion list
tab        complete the selected slash command or @file reference
ctrl+r     search prompt history
ctrl+o     toggle folded/expanded transcript rendering
ctrl+t     focus the next tool call in the transcript
ctrl+d     expand/collapse the focused tool call detail
ctrl+w     delete the previous word
ctrl/alt+← move to the previous word
ctrl/alt+→ move to the next word
ctrl+u     clear text before the cursor
ctrl+k     clear text after the cursor
esc        close the active picker or clear current input
```

`/model` opens a filterable model picker. `/model <profile>` still switches directly. If a turn is running, normal user messages are queued and sent after the current turn finishes.

The terminal UI streams reasoning/text deltas while a turn is running, shows retry attempts as status events, renders assistant Markdown/list/table/code output, previews patch/git diffs, supports @file references, and keeps tool approval/detail rendering separate from the agent core.

Run tests:

```bash
make test
```

Check local readiness and configured model profiles:

```bash
make doctor
agents doctor
agents doctor --json
```

`agents doctor` reports model profile names, protocol/model/endpoint, workspace root, sandbox mode, database mode, terminal/web toolchain status, and web search readiness. It never prints API keys.

Run the full local test suite before delivery:

```bash
make test
```

## Configuration

Kernel, platform, bridge, and server share runtime configuration through `agents.kernel.config`.
`agents.interfaces.server.core.config.settings` is the service-facing aggregate that adds server/logging settings on top of the shared agent config.

Non-secret defaults are committed in `config/defaults.toml`. Local non-secret overrides belong in `config/local.toml`, which is gitignored. `.env` should stay focused on tokens, secrets, and deployment-only overrides.

Precedence:

```text
class fallback < config/defaults.toml < config/local.toml < .env / shell env < request AgentSpec
```

Override config file paths when needed:

```bash
AGENTS_DEFAULT_CONFIG=config/defaults.toml
AGENTS_LOCAL_CONFIG=config/local.toml
```

| Domain | Env prefix | Common fields |
|---|---|---|
| `settings.agent` | `AGENT_` | `AGENT_PROTOCOL`, `AGENT_MAX_TOKENS`, `AGENT_MAX_RETRIES`, `AGENT_ENABLED_TOOLS`, `AGENT_SKILLS`, `AGENT_WORKSPACE_ROOT`, `AGENT_SANDBOX_PROVIDER`, `AGENT_RUN_STORE`, `AGENT_RUN_ROOT`, `AGENT_DB_PATH` |
| `settings.models.openai` | `OPENAI_` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` |
| `settings.models.openai_responses` | `OPENAI_RESPONSES_` | `OPENAI_RESPONSES_API_KEY`, `OPENAI_RESPONSES_BASE_URL`, `OPENAI_RESPONSES_MODEL` |
| `settings.models.anthropic` | `ANTHROPIC_` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` |
| `settings.models.gemini` | `GEMINI_` | `GEMINI_API_KEY`, `GEMINI_BASE_URL`, `GEMINI_MODEL` |
| `settings.mcp` | `MCP_` | `MCP_SERVER_NAME`, `MCP_SERVER_COMMAND`, `MCP_CLIENT_TIMEOUT`, `MCP_EXECUTION_MODE` |
| `settings.web_search` | `WEB_SEARCH_` | `WEB_SEARCH_PROVIDER`, `WEB_SEARCH_TAVILY_API_KEY`, `WEB_SEARCH_MAX_RESULTS`, `WEB_SEARCH_MAX_CREDITS_PER_RUN` |

Model protocol names:

| Protocol | Wire API |
|---|---|
| `openai-chat` | OpenAI Chat Completions |
| `openai-responses` | OpenAI Responses API |
| `claude-messages` | Anthropic Claude Messages |
| `gemini` | Gemini Generate Content |

Claude-compatible config prefers project-owned `AGENT_CLAUDE_*` values before falling back to ambient `ANTHROPIC_*` values.

The terminal app builds `/model` choices from configured model profile groups. The standard groups are `OPENAI_*`, `OPENAI_RESPONSES_*`, `AGENT_CLAUDE_*`, and `GEMINI_*`. For named OpenAI-compatible endpoints such as Kimi, add a profile group:

```bash
AGENT_MODEL_PROFILES=kimi
AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2
AGENT_MODEL_PROFILE_KIMI_API_KEY=
AGENT_MODEL_PROFILE_KIMI_ALIASES=moonshot
```

Then switch the whole protocol/base URL/model/key group with `/model kimi`, or start directly with `make terminal ARGS="--model-profile kimi"`.

Run records use memory by default. To keep run records as local JSON files:

```bash
AGENT_RUN_STORE=file
AGENT_RUN_ROOT=.agents/runs
```

To persist runs, runtime events, approval checkpoints, approval audit, trace spans, and long-term domain records in one local database:

```bash
AGENT_RUN_STORE=sqlite
AGENT_DB_PATH=.agents/agents.db
```

## Sandbox And Workspace Model

The agent runtime does not run inside the sandbox. Runtime, server, model calls, credentials, approval state, traces, and audit records stay in the control plane. The sandbox is the execution plane for high-risk native tools.

```text
model -> runtime -> tool registry -> builtin tool -> SandboxClient -> local/docker execution -> workspace
```

The persistent data boundary is the workspace. Scope and disk layout are intentionally separate: the runtime records `tenant_id`, `user_id`, `agent_id`, and `workspace_id` for permissions, memory, audit, and database joins, while the local filesystem path is selected by the workspace layout.

```text
local/dev default: .agents/workspaces/local/default
local named workspace: .agents/workspaces/local/{workspace_id}
scoped/cloud: .agents/workspaces/{tenant_id}/{user_id}/{agent_id}/{workspace_id}
```

`AGENT_WORKSPACE_LAYOUT=auto` is the default. It uses the compact local layout for placeholder identities and switches to the scoped layout when real tenant/user identity is provided. `local` and `scoped` can be selected explicitly when a deployment needs one behavior.

The sandbox gets a lease against that workspace. Profiles provide conservative defaults:

| Profile | Default behavior |
|---|---|
| `restricted` | Read-only workspace access. |
| `coding` | File write plus allowlisted coding commands such as `git`, `python3`, `pytest`, and `make`. |
| `test` | Process execution for common test commands. |
| `browser` | Browser-oriented process and network access. |

With the local provider, tools execute directly inside the resolved workspace path. With the Docker provider, each command runs with the workspace mounted at `/workspace` by default:

```bash
AGENT_SANDBOX_PROFILE=coding
AGENT_SANDBOX_PROVIDER=docker
AGENT_SANDBOX_IMAGE=python:3.12-slim
AGENT_SANDBOX_ALLOW_FILE_WRITE=true
AGENT_SANDBOX_ALLOW_PROCESS=true
AGENT_SANDBOX_ALLOWED_COMMANDS=git,pytest,python3
```

Builtin tools are semantic APIs, not direct container controls:

| Tool | Default risk | Notes |
|---|---|---|
| `filesystem.read`, `filesystem.list` | low | Enabled by default. |
| `search.grep` | low | Read-only regex search over workspace text files. |
| `filesystem.write` | medium | Requires `AGENT_SANDBOX_ALLOW_FILE_WRITE=true` and tool enablement. |
| `filesystem.delete`, `filesystem.move` | medium | Native workspace file operations; guarded by file-write policy and approval. |
| `patch.apply` | medium | Applies exact text edits and file creates; returns a unified diff. |
| `web.search`, `web.extract` | medium | Control-plane Tavily-backed search/extraction; API key does not enter sandbox. |
| `web.map` | high | Control-plane site URL discovery; not enabled by default. |
| `git.status`, `git.diff`, `git.log`, `git.show` | low/high | Git inspection through the sandbox. Diff/history output is truncated to a safe bound. |
| `git.add`, `git.commit` | high | Native git mutation tools; guarded by process, file-write policy, and approval. |
| `test.discover` | low | Inspects workspace markers and suggests likely test commands without running them. |
| `test.run` | high | Runs an allowlisted test command. |
| `browser.open`, `browser.download` | high | Requires file write, process, and network permission; stores internal outputs in the run artifact store unless an explicit workspace path is provided. |
| `shell.run` | high | Fallback escape hatch; prefer native tools. |

Network-capable tools have two execution modes. `web.search`, `web.extract`, and `web.map` are control-plane tools for API-backed information retrieval; provider credentials and credit policy stay outside the sandbox. `browser.open` and `browser.download` execute through sandbox process/network permission. Internal fetches, screenshots, raw pages, and logs are stored in the control-plane artifact blob store; explicit user-requested paths still write normal workspace files. Full interactive browser tools such as click/type/screenshot still need a dedicated browser runtime provider.

Approval events include a tool impact payload with risk, paths, commands, network domains, write flags, external disclosure flags, cost estimates, and patch previews. Approval audit records persist the same impact payload for later review.

MCP stdio tools currently run as trusted control-plane extensions by default and are tagged with `MCP_EXECUTION_MODE` metadata. Untrusted local MCP servers should not be enabled until a sandboxed MCP provider is configured.

Workspace files and runtime artifacts are separate. User deliverables stay in the workspace. Tool artifacts are run-scoped control-plane blobs and are indexed by `artifact_records`; file bodies do not live in the workspace unless the user explicitly asks for a workspace path.

Local terminal sessions use an ephemeral in-memory control plane and write artifact files under a per-project cache:

```text
~/.agents/projects/{workspace_hash}/runs/{run_id}/artifacts/downloads/
~/.agents/projects/{workspace_hash}/runs/{run_id}/artifacts/screenshots/
~/.agents/projects/{workspace_hash}/runs/{run_id}/artifacts/logs/
~/.agents/projects/{workspace_hash}/runs/{run_id}/artifacts/raw/
```

The HTTP server uses durable SQLite-backed control-plane state by default. Its local artifact blob root is scoped by tenant/user/agent/workspace and can later be replaced with object storage without changing the tool contract:

```text
.agents/server/artifacts/{tenant_id}/{user_id}/{agent_id}/{workspace_id}/runs/{run_id}/artifacts/downloads/
```

The database stores artifact references in `artifact_records`: URI, hash, size, kind, role, run id, task id, and tool call id. Sandbox runs still record workspace snapshots before and after tool execution, but snapshots skip `.agents`, `.git`, `.venv`, `node_modules`, and `__pycache__` so internal runtime state is not reported as user code changes.

## HTTP API

Non-streaming:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "hello",
    "protocol": "openai-chat",
    "model": "gpt-4o"
  }'
```

Response data includes:

```json
{
  "run_id": "run_...",
  "status": "finished",
  "content": "...",
  "messages": [],
  "tool_results": [],
  "events": []
}
```

Streaming:

```bash
curl -N -X POST http://127.0.0.1:8010/api/v1/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}'
```

The first SSE event is always `run_created`:

```text
event: run_created
data: {"type":"run_created","name":"run","payload":{"run_id":"run_..."}}
```

Then the stream emits runtime events such as `text_delta`, `reasoning_delta`, `tool_approval_required`, `tool_approval_decision`, `tool_start`, `tool_result`, `error`, and `done`.

Create and run a long-running task through the server:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/agent/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Inspect workspace","message":"List the files in my workspace"}'

curl -X POST http://127.0.0.1:8010/api/v1/agent/tasks/task_.../run
```

Task records contain task status, step status, the backing `run_id`, and the final step output. This is the durable task layer that future background workers and schedule runners build on.

Query a run:

```bash
curl http://127.0.0.1:8010/api/v1/agent/runs/run_...
```

The response contains the run scope, status, timestamps, metadata, and recorded runtime events.

Query the trace timeline for the same run:

```bash
curl http://127.0.0.1:8010/api/v1/agent/runs/run_.../trace
```

The response contains ordered trace spans for run/model/tool/approval activity, approval audit decisions, and `sandbox_events` for run-scoped tool execution. Trace spans are operational observability; approval audit records are the stable accountability trail.

### Tool Approval

Tool permissions are part of `AgentSpec`, not UI state. Request bodies can set:

```json
{
  "message": "inspect the workspace",
  "permission_profile": "ask",
  "enabled_tools": ["filesystem.read"]
}
```

Modes:

| Mode | Behavior |
|---|---|
| `auto` | Execute allowed tools without pausing. |
| `ask` | Pause before tool execution and emit `tool_approval_required`. |
| `deny` | Return denied tool results without executing tools. |

Builtin tools are registered for every session, but only configured enabled tools are sent to the model. The default `AGENT_BUILTIN_TOOLS` is `filesystem.read,filesystem.list`. `filesystem.write` and `shell.run` are available only when enabled and allowed by sandbox settings.

When a tool requires approval, the run is marked `awaiting_approval` and the runtime checkpoint keeps the pending tool calls. Resume the same run:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/agent/runs/run_.../approval \
  -H 'Content-Type: application/json' \
  -d '{"tool_call_ids":["call_..."],"approved":true}'
```

The web UI uses this endpoint for the Approve/Deny panel. The server owns the HTTP flow; `agents.kernel.runtime` owns the pause/resume semantics.

## Agent And Run Model

External callers construct an `AgentSpec`. The spec carries:

- model override: protocol, model, base URL, API key
- workspace scope: tenant, user, agent, workspace
- enabled tools and skills
- tool permission mode/rules and memory profile names
- metadata

Server routes and the terminal bridge convert request/options into `AgentSpec`, then call:

```python
from agents.kernel.assembly import create_agent_session, create_agent_session_async
```

Each chat request creates a new run. `run_id` is generated by `agents.platform.sessions.RunService` and passed into `AgentSession.send()` or `AgentSession.stream()`. Runtime checkpoints, platform run records, trace spans, and approval audit records share that same ID. In file mode, each run is stored as one JSON document under `AGENT_RUN_ROOT`. In SQLite mode, runs, runtime events, checkpoints, trace spans, approval audit records, and long-term domain records share `AGENT_DB_PATH`.

SQLite domain tables:

| Table | Purpose |
|---|---|
| `tenants`, `users` | Identity scope used by later server auth. |
| `agent_profiles` | Stored agent definitions without API keys. |
| `workspace_records` | Workspace ownership, path, status, and metadata. |
| `artifact_records` | Run-scoped tool artifacts and workspace-output references; stores URI, hash, size, type, and tool call linkage. |
| `memory_records` | User, agent, workspace, and run-scoped memories. |
| `tasks`, `task_steps`, `task_attempts` | Long-running task state, step lifecycle, and retry attempts. |
| `sandbox_leases`, `sandbox_events`, `sandbox_workspace_snapshots` | Sandbox execution leases, tool execution events, and workspace diff snapshots. |
| `credential_refs` | References to secrets stored elsewhere; raw secrets are not stored here. |

Defaults for local development:

```text
tenant_id    default
user_id      anonymous
agent_id     default
workspace_id default
path         .agents/workspaces/local/default
run_id       generated per request
```

## Web UI

Build and serve through the server:

```bash
cd apps/web && npm run build
make run
```

When `apps/web/dist/` exists, the server mounts it at `/ui/` and redirects `/` to `/ui/`.

For frontend development:

```bash
make dev-web
```

## Development Rules

- Put agent kernel logic in `src/agents/kernel/`, not in platform, interfaces, or apps.
- Put shared run/session/persistence/profile control code in `src/agents/platform/`.
- Put HTTP/SSE/auth/static protocol code in `src/agents/interfaces/server/`.
- Put local NDJSON protocol code in `src/agents/interfaces/bridge/`.
- Add model protocol adapters under `agents.kernel.models.adapters`; keep shared stream semantics in `agents.kernel.models.protocol`.
- Add tools under `agents.kernel.capabilities.tools` or load them through MCP.
- Route host-affecting tools through `agents.kernel.capabilities.sandbox`; do not let tools touch host paths or subprocesses directly.
- Add new context sources through `agents.kernel.context.sources`.
- Add long-running task orchestration under `agents.kernel.tasks`; keep server APIs as adapters.
- Add new run persistence backends by implementing `agents.kernel.state.runs.RunStore`; checkpoint, trace, and approval audit storage should stay behind their own store interfaces. The platform should compose stores, and interfaces should only call adapters.
- Add identity/auth from server login state later; do not trust user-supplied `tenant_id` or `user_id` in cloud mode.
