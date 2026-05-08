# 🚀 Quickstart Guide

Get up and running with Agents in under 5 minutes.

---

## 📋 Prerequisites

- **Python 3.10+**
- **Node.js 18+** (for Web UI, optional)
- **Bun** (for terminal UI development, optional)
- **Docker** (for sandbox isolation, optional)

---

## 📦 Installation

### Step 1: Clone & Install

```bash
git clone https://github.com/Pixeldooooog/Agents.git
cd Agents
make setup
```

`make setup` installs:
- Python dependencies (kernel, platform, server)
- Web frontend dependencies (if `npm` available)
- Terminal app dependencies (if `bun` available)

### Step 2: Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and add at least one model provider's API key:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Google Gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-1.5-pro
```

For named OpenAI-compatible endpoints (Kimi, DeepSeek, etc.), see [Configuration](configuration.md#custom-model-profiles).

---

## 🚀 Launch

### Terminal Interface (Recommended)

```bash
agents tui
```

This launches the TypeScript Ink terminal frontend with:
- Local Python bridge
- Current directory bound as workspace
- Coding tools enabled
- Approval prompts for write/execute operations

### Web Interface

```bash
agents gui
```

This serves the web UI through the local HTTP/SSE service. If the web build is missing, it will build `apps/web` first.

Access at `http://localhost:8000/ui`

---

## 🎯 Your First Agent

### Option 1: Through TUI

Just type your question:

```
> Read the README and tell me what this project does
```

The agent will use built-in tools to read files and respond.

### Option 2: Through Python API

```python
import asyncio
from agents.kernel.specs import AgentSpec
from agents.kernel.runtime import AgentRuntime

async def main():
    spec = AgentSpec(
        model="gpt-4",
        tools=["file_read", "file_list", "web_search"]
    )
    
    runtime = AgentRuntime(spec)
    result = await runtime.run("Analyze this project structure")
    
    print(result.content)

asyncio.run(main())
```

### Option 3: Through HTTP API

Start the server:

```bash
make run
```

Then call the API:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Hello, agent!",
    "protocol": "openai-chat",
    "model": "gpt-4"
  }'
```

For streaming:

```bash
curl -N -X POST http://127.0.0.1:8010/api/v1/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello, agent!"}'
```

---

## 🛠️ Common Commands

### Terminal Commands

While in `agents tui`, use these slash commands:

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | Show protocol, workspace, permission, tokens |
| `/model` | List and switch model profiles |
| `/doctor` | Check local readiness |
| `/workspace` | Show workspace path |
| `/tools` | List enabled tools |
| `/context` | Show context window usage |
| `/trace` | Show context assembly trace |
| `/fold` / `/unfold` | Collapse/expand long blocks |
| `/clear` | Reset conversation |
| `/exit` | Leave the chat |

### Terminal Shortcuts

| Shortcut | Action |
|----------|--------|
| `↑` / `↓` | Browse history or navigate pickers |
| `Tab` | Complete commands or `@file` references |
| `Ctrl+R` | Search prompt history |
| `Ctrl+O` | Toggle folded transcript |
| `Ctrl+T` | Focus next tool call |
| `Ctrl+D` | Expand/collapse focused tool |
| `Esc` | Close picker or clear input |

### CLI Switches

```bash
# Profile selection
agents tui --profile chat       # Read-oriented
agents tui --profile coding     # Default coding profile
agents tui --profile browser    # Coding + browser/web tools

# Permission modes
agents tui --permission auto      # No approval prompts
agents tui --permission guarded   # Confirm writes/commands

# Workspace
agents tui --workspace-path ./my-project

# Tool selection
agents tui --tools filesystem.read,patch.apply,test.run

# Model profile
agents tui --model-profile kimi
```

---

## 🩺 Health Check

Verify your installation:

```bash
agents doctor
```

Or with JSON output:

```bash
agents doctor --json
```

This reports:
- Configured model profile names
- Protocol/model/endpoint status
- Workspace root
- Sandbox mode
- Database mode
- Terminal/web toolchain status
- Web search readiness

API keys are never printed.

---

## 🧪 Run Tests

```bash
# All tests
make test

# Specific module
pytest tests/kernel/test_runtime.py

# With coverage
pytest --cov=agents
```

---

## 📚 Next Steps

- **[Features](features.md)** — Deep dive on tools, models, approvals, memory
- **[Use Cases](use-cases.md)** — Real-world examples with full code
- **[Configuration](configuration.md)** — All env vars and profiles
- **[Architecture](architecture.md)** — System design

---

## 🐛 Troubleshooting

### "Command not found: agents"

Make sure you installed with `pip install -e .` and your Python environment is active.

### "No module named 'agents'"

Run `make setup` to install all dependencies, or manually:

```bash
pip install -e .
```

### Terminal UI doesn't start

Check if `bun` is installed:

```bash
bun --version
```

Or use the Python fallback:

```bash
make bridge-fallback
```

### Web UI 404

Build the web frontend:

```bash
make build-web
agents gui
```

### Model API errors

Run `agents doctor` to verify your API keys and endpoints are configured correctly.
