# 🎯 Use Cases

Real-world examples showing how to build different types of agents.

---

## 👨‍💻 Code Assistant

An agent that can read, analyze, and modify codebases.

### Capabilities
- Read and search code files
- Generate diffs and apply patches
- Run tests and check Git status
- Suggest refactorings

### Configuration

```python
from agents.kernel.specs import AgentSpec
from agents.kernel.runtime import AgentRuntime

spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=[
        "file_read",
        "file_list",
        "file_write",
        "patch_apply",
        "text_search",
        "git_status",
        "git_diff",
        "git_log",
        "test_run",
    ],
    tool_approval_mode="ask",  # Confirm writes
    workspace_id="my_project"
)

runtime = AgentRuntime(spec)
result = await runtime.run(
    "Find all uses of the deprecated `old_api()` function and replace them with `new_api()`"
)
```

### Through TUI

```bash
agents tui --profile coding
```

Then in the chat:
```
> @src/main.py review this file for potential issues
> refactor the database access layer to use async/await
> run the tests and fix any failures
```

---

## 📊 Data Analysis Pipeline

An agent that fetches, processes, and analyzes data.

### Capabilities
- Web search for data sources
- Extract structured data from web pages
- Save and process datasets
- Generate analysis reports

### Configuration

```python
spec = AgentSpec(
    model="gpt-4-turbo",
    tools=[
        "web_search",
        "web_extract",
        "web_fetch",
        "file_write",
        "file_read",
    ],
    skills=["data_analysis"],
    workspace_id="research_q1"
)

runtime = AgentRuntime(spec)
result = await runtime.run("""
    1. Search for the latest 2025 AI startup funding data
    2. Extract company names, funding amounts, and investors
    3. Save as CSV in data/funding.csv
    4. Generate a summary report with key trends
""")
```

### Example Workflow

```python
# Multi-step data pipeline
queries = [
    "Find top 10 Python web frameworks of 2025",
    "Extract GitHub stars and last commit dates for each",
    "Compare with last year's data and identify trends",
    "Generate a markdown report",
]

for query in queries:
    result = await runtime.run(query)
    print(f"✓ {query}")
```

---

## 🔧 DevOps Automation

An agent that monitors systems, diagnoses issues, and executes fixes.

### Capabilities
- Read logs and config files
- Execute shell commands
- Git operations
- Network requests for monitoring APIs

### Configuration

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=[
        "shell",
        "file_read",
        "file_list",
        "web_fetch",
        "git_status",
    ],
    tool_approval_mode="ask",  # CRITICAL: Always confirm shell ops
    tool_permissions={
        "shell": {
            "commands": ["systemctl", "docker", "kubectl", "git"],
            "deny_commands": ["rm", "dd", "mkfs"]
        },
        "file_read": {
            "paths": ["/var/log/*", "/etc/*", "./*"]
        }
    }
)

runtime = AgentRuntime(spec)
result = await runtime.run(
    "Check the nginx error logs from the last hour and identify any patterns"
)
```

### Incident Response Example

```python
# Automated incident triage
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["shell", "file_read", "web_fetch"],
    tool_approval_mode="ask",
    memory_enabled=True,  # Remember past incidents
)

runtime = AgentRuntime(spec)

# Initial diagnosis
diagnosis = await runtime.run("""
    The API service is returning 503 errors. Please:
    1. Check service status
    2. Review recent logs
    3. Identify potential causes
    4. Suggest remediation steps (don't execute yet)
""")

print(diagnosis.content)

# After review, execute fix
fix = await runtime.run("Apply the recommended fix and verify recovery")
```

---

## 🔬 Research Assistant

An agent that searches, summarizes, and maintains long-term memory.

### Capabilities
- Web search and content extraction
- Document summarization
- Cross-reference past research
- Generate structured reports

### Configuration

```python
spec = AgentSpec(
    model="gpt-4-turbo",
    tools=[
        "web_search",
        "web_extract",
        "web_fetch",
        "file_write",
        "file_read",
    ],
    memory_enabled=True,  # Remember past research
    context_window_tokens=128000,
    workspace_id="research_lab"
)

runtime = AgentRuntime(spec)

# Initial research
result = await runtime.run("""
    Research the current state of vector databases in 2025.
    Focus on: performance benchmarks, popular options, use cases.
    Save findings to research/vector_db_2025.md
""")

# Follow-up uses memory
followup = await runtime.run(
    "Based on what you found, which vector DB would you recommend for a 10M document RAG system?"
)
```

---

## 🤖 Custom MCP Tool Integration

Extend agents with custom tools via Model Context Protocol.

### Create an MCP Server

```python
# my_mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my_tools")

@mcp.tool()
async def query_database(sql: str) -> str:
    """Execute a SQL query and return results."""
    # Your database logic
    return execute_query(sql)

@mcp.tool()
async def send_slack_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel."""
    # Your Slack logic
    return f"Sent to {channel}"

if __name__ == "__main__":
    mcp.run()
```

### Use in an Agent

```python
from agents.kernel.capabilities.tools import load_mcp_server

# Load custom tools
await load_mcp_server("./my_mcp_server.py")

spec = AgentSpec(
    model="gpt-4",
    tools=["query_database", "send_slack_message"]
)

runtime = AgentRuntime(spec)
result = await runtime.run(
    "Query the users table for new signups today and post a summary to #alerts"
)
```

---

## 🧪 Multi-Step Task with Approvals

Long-running task with checkpoint/resume.

### Configuration

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["file_write", "shell", "git_status", "git_diff"],
    tool_approval_mode="ask",
    checkpoint_enabled=True,
)

runtime = AgentRuntime(spec)
```

### Through HTTP API

Create a task:

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Database migration",
    "message": "Run the schema migration for v2.0"
  }'
```

Run it:

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/tasks/task_xyz/run
```

Approve when prompted:

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/runs/run_abc/approval \
  -H 'Content-Type: application/json' \
  -d '{"tool_call_ids":["call_123"],"approved":true}'
```

---

## 📝 Document Processing Pipeline

Process and summarize documents at scale.

### Configuration

```python
import asyncio
from pathlib import Path

spec = AgentSpec(
    model="gpt-4",
    tools=["file_read", "file_write"],
    workspace_id="doc_processing"
)

runtime = AgentRuntime(spec)

# Process all PDFs in a directory
async def process_documents(folder: Path):
    for doc in folder.glob("*.txt"):
        result = await runtime.run(f"""
            Read {doc.name} and:
            1. Generate a 200-word summary
            2. Extract key dates and entities
            3. Save as {doc.stem}_summary.md
        """)
        print(f"✓ Processed {doc.name}")

asyncio.run(process_documents(Path("./documents")))
```

---

## 🌐 Browser Automation

Navigate and extract data from web pages.

### Configuration

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=[
        "web_search",
        "web_fetch",
        "web_extract",
        "browser_open",
        "browser_download",
    ],
    sandbox_profile="browser",
)

runtime = AgentRuntime(spec)
result = await runtime.run("""
    1. Navigate to https://news.ycombinator.com
    2. Extract the top 10 stories
    3. For each story with >100 points, fetch the article
    4. Generate a daily digest
""")
```

---

## 💡 Tips for Building Effective Agents

### 1. Start with Minimal Tools
Don't enable all tools by default. Add only what's needed:

```python
# ❌ Too permissive
tools=["file_read", "file_write", "shell", "web_search", "git_commit"]

# ✅ Focused
tools=["file_read", "file_list"]  # Add more as needed
```

### 2. Use Approval Mode for Risky Operations

```python
spec = AgentSpec(
    tools=["shell", "file_write"],
    tool_approval_mode="ask",  # Always confirm
)
```

### 3. Scope Permissions

```python
tool_permissions={
    "file_write": {"paths": ["/safe/dir/*"]},
    "shell": {"commands": ["git", "npm"]}
}
```

### 4. Enable Memory for Multi-Session Workflows

```python
spec = AgentSpec(
    memory_enabled=True,
    workspace_id="long_term_project"
)
```

### 5. Use Workspace Isolation

```python
# Different agents, different workspaces
researcher = AgentSpec(workspace_id="research")
coder = AgentSpec(workspace_id="codebase")
```

---

## 📚 Next Steps

- **[Features](features.md)** — Deep dive on each capability
- **[Configuration](configuration.md)** — Customize behavior
- **[Architecture](architecture.md)** — Understand the internals
