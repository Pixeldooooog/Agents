<div align="center">

<img src="assets/logo-subtle.svg" alt="AGENTS" width="600">


### 🚀 Production-Grade AI Agent Framework

**Build intelligent agents that think, act, and learn**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[Quick Start](#-quick-start) • [Features](#-features) • [Architecture](#-architecture) • [Documentation](#-documentation) • [中文文档](README.zh-CN.md)

</div>

---

## 🎯 What is Agents?

**Agents** is an AI agent framework built around **clean architecture principles**.

Strict layered boundaries. Zero hidden coupling. Readable from day one.

<table>
<tr>
<td width="33%" valign="top">

### 🏛️ **Clean Architecture**
Strict kernel/platform/interface layers with zero circular dependencies

</td>
<td width="33%" valign="top">

### 🧠 **Multi-Model**
Unified interface for OpenAI, Claude, Gemini with protocol-neutral streaming

</td>
<td width="33%" valign="top">

### 🛠️ **Rich Tooling**
File ops, Git, web search, shell execution, plus MCP protocol support

</td>
</tr>
<tr>
<td width="33%" valign="top">

### 🔒 **Secure by Default**
Sandbox isolation, approval workflows, workspace separation

</td>
<td width="33%" valign="top">

### ⚡ **Real-Time**
Stream text, reasoning, and tool execution as they happen

</td>
<td width="33%" valign="top">

### 🎨 **Dual UI**
Terminal TUI for devs, Web UI for visual workflows

</td>
</tr>
</table>

---

## ⚡ Quick Start

```bash
# Clone
git clone https://github.com/Pixeldooooog/Agents.git
cd Agents

# Install
pip install -e .

# Configure (add your API keys)
cp .env.example .env

# Launch terminal interface
agents tui

# Or launch web interface
agents gui
```

### Your First Agent in 30 Seconds

```python
from agents.kernel.specs import AgentSpec
from agents.kernel.runtime import AgentRuntime

# Define capabilities
spec = AgentSpec(
    model="gpt-4",
    tools=["file_read", "web_search", "file_write"]
)

# Run
runtime = AgentRuntime(spec)
result = await runtime.run("Find the latest Python best practices and create a summary")
```

**[📖 Full Quickstart Guide →](docs/quickstart.md)**

---

## 📦 Build & Delivery

```bash
# Validate backend + terminal tests
make check

# Build Python artifacts (sdist + wheel) and verify metadata
make package

# Build web assets
make build-web

# Build deployment image
make build
```

---

## ✨ Features

<details open>
<summary><b>🤖 Multi-Model Support</b></summary>

Seamlessly switch between model providers with a unified interface:

```python
# OpenAI
spec = AgentSpec(model="gpt-4-turbo")

# Anthropic Claude
spec = AgentSpec(model="claude-3-5-sonnet")

# Google Gemini
spec = AgentSpec(model="gemini-1.5-pro")
```

All models support streaming, tool calling, and reasoning display.

</details>

<details>
<summary><b>🛠️ Powerful Tool System</b></summary>

**Built-in Tools:**
- 📁 File operations (read/write/patch)
- 🔍 Text and web search
- 🌐 Web scraping and extraction
- 🔧 Git integration
- 💻 Shell execution
- 🧪 Test runners

**Extend with MCP:**
```python
from agents.kernel.capabilities.tools import load_mcp_server

await load_mcp_server("./my_custom_tools.py")
```

</details>

<details>
<summary><b>✋ Human-in-the-Loop Approvals</b></summary>

Control sensitive operations with approval workflows:

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["file_write", "shell"],
    tool_approval_mode="ask",  # Pause and ask before executing
    tool_permissions={
        "file_write": {"paths": ["/safe/dir/*"]},
        "shell": {"commands": ["git", "npm", "pytest"]}
    }
)
```

Agents pause execution and wait for your approval via TUI or Web UI.

</details>

<details>
<summary><b>🧠 Memory & Context Management</b></summary>

Long-running conversations with automatic context handling:

```python
spec = AgentSpec(
    model="gpt-4",
    memory_enabled=True,
    context_window_tokens=128000
)
```

- Retrieve relevant memories from past sessions
- Automatic context compaction when approaching limits
- Maintain coherence across restarts

</details>

<details>
<summary><b>🔒 Sandbox Isolation</b></summary>

Safe execution with workspace isolation:

```python
spec = AgentSpec(
    sandbox_mode="docker",  # or "local"
    workspace_id="project_alpha"
)
```

Each agent runs in an isolated environment with controlled file system access.

</details>

**[📚 Full Feature Documentation →](docs/features.md)**

---

## 🎨 Interfaces

<table>
<tr>
<td width="50%">

### 💻 Terminal UI

```bash
agents tui
```

**Perfect for developers:**
- Streaming text and reasoning
- Tool execution timeline
- Approval prompts
- `@file` context injection
- Model switching
- Command history

</td>
<td width="50%">

### 🌐 Web UI

```bash
agents gui
```

**Visual workspace:**
- Chat interface
- Activity timeline
- Run inspector with traces
- Approval controls
- Settings panel
- Artifact viewer

</td>
</tr>
</table>

---

## 🏗️ Architecture

**Architecture is not an afterthought — it's the foundation.**

Agents is organized around strict boundaries that make the system understandable, testable, and maintainable as it grows.

<div align="center">

<pre>
┌─────────────────────────────────────────┐
│         Apps (Terminal / Web)           │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      Interfaces (HTTP/SSE, NDJSON)      │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   Platform (Sessions, Persistence)      │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Kernel (Models, Runtime, Tools, etc)   │
│  ✓ Zero dependency on web/UI layers    │
└─────────────────────────────────────────┘
</pre>

</div>

**Design Principles:**
- 🎯 **Separation of Concerns** — Kernel is pure SDK, no web/UI dependencies
- 🔌 **Protocol Neutral** — Abstract model provider differences
- 🔐 **Security First** — Sandbox execution, secret redaction, approval gates
- 📦 **Pluggable Storage** — Memory, JSON, or SQLite backends
- 🧪 **Fully Tested** — Comprehensive test coverage for core components

**[🏛️ Architecture Deep Dive →](docs/architecture.md)**

---

## 🎯 Use Cases

<table>
<tr>
<td width="50%">

### 👨‍💻 **Code Assistant**
Read, analyze, and modify codebases with Git integration

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["file_read", "file_write",
           "git_status", "patch_apply"]
)
```

</td>
<td width="50%">

### 📊 **Data Pipeline**
Fetch, process, and analyze data with web scraping

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["web_search", "web_extract",
           "file_write"],
    skills=["data_analysis"]
)
```

</td>
</tr>
<tr>
<td width="50%">

### 🔧 **DevOps Automation**
Monitor, diagnose, and fix with shell access

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["shell", "file_read"],
    tool_approval_mode="ask"
)
```

</td>
<td width="50%">

### 🔬 **Research Assistant**
Search, summarize, and maintain memory

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["web_search", "file_read"],
    memory_enabled=True
)
```

</td>
</tr>
</table>

**[📖 Detailed Use Cases & Examples →](docs/use-cases.md)**

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[Quickstart Guide](docs/quickstart.md)** | Installation, configuration, and first agent |
| **[Features](docs/features.md)** | Deep dive on tools, models, approvals, memory |
| **[Use Cases](docs/use-cases.md)** | Real-world examples with full code |
| **[Configuration](docs/configuration.md)** | Environment variables, profiles, storage |
| **[Architecture](docs/architecture.md)** | System design and package boundaries |
| **[Technical Design](docs/technical-design.md)** | Control/data planes and sandbox design |
| **[Module Map](docs/module-map.md)** | Module responsibilities and extension points |
| **[Roadmap](docs/roadmap.md)** | Development plan and upcoming features |

---

## 🛠️ Development Status

### ✅ **Production Ready**

- ✓ Multi-model streaming (OpenAI, Claude, Gemini)
- ✓ Tool execution with sandbox isolation
- ✓ Approval workflows with checkpoint/resume
- ✓ Terminal and Web interfaces
- ✓ MCP tool integration
- ✓ Memory and context compaction
- ✓ SQLite persistence and tracing

### 🚧 **Coming Soon**

- Multi-agent orchestration (planner/worker/reviewer)
- Hosted authentication and account system
- Managed sandbox pool scheduling
- Advanced browser automation
- Billing and rate limiting

---

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Follow the [architecture rules](docs/architecture.md#development-rules)
4. Add tests for new functionality
5. Submit a pull request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🌟 Star History

If you find Agents useful, please consider giving it a star! ⭐

---

<div align="center">

**Built with ❤️ using FastAPI, Typer, Pydantic, and MCP**

[Report Bug](https://github.com/Pixeldooooog/Agents/issues) • [Request Feature](https://github.com/Pixeldooooog/Agents/issues) • [Discussions](https://github.com/Pixeldooooog/Agents/discussions)

</div>
