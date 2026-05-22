import asyncio
import json
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.specs import AgentSpec


def _registry_for_workspace(
    root: Path,
    *,
    agent_metadata: dict | None = None,
    file_reading_limits: dict | None = None,
) -> ToolRegistry:
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=root,
        path=root,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=AgentSpec(metadata=agent_metadata or {}),
        file_reading_limits=file_reading_limits or {},
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    return registry


def test_filesystem_read_rejects_token_heavy_text_before_recording_full_read(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("abcdefghijklmnopqrstuvwxyz\nok\n", encoding="utf-8")
    registry = _registry_for_workspace(tmp_path, agent_metadata={"fileReadingLimits": {"maxTokens": 2}})

    full = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    limited = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "offset": 2, "limit": 1}))
    write = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert full.is_error is True
    assert "exceeds maximum allowed tokens (2)" in full.content
    assert "Use offset and limit parameters" in full.content
    assert limited.is_error is False
    assert limited.raw["content"] == "ok\n"
    assert limited.raw["isPartialView"] is True
    assert write.is_error is True
    assert "File has not been read yet" in write.content


def test_filesystem_read_uses_context_size_limit_unless_explicit_max_bytes(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    registry = _registry_for_workspace(tmp_path, file_reading_limits={"max_size_bytes": 8})

    default_full = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    limited = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "limit": 1}))
    explicit_full = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "max_bytes": 64}))

    assert default_full.is_error is True
    assert "exceeds maximum allowed size (8 B)" in default_full.content
    assert "Use offset and limit parameters" in default_full.content
    assert explicit_full.is_error is False
    assert explicit_full.raw["content"] == "one\ntwo\nthree\n"
    assert explicit_full.raw["isPartialView"] is False
    assert limited.is_error is False
    assert limited.raw["content"] == "one\n"


def test_notebook_read_uses_cells_json_size_limit(tmp_path: Path):
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# Title\n", "More notebook content\n"],
                "metadata": {},
            }
        ],
        "metadata": {},
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    registry = _registry_for_workspace(tmp_path, agent_metadata={"fileReadingLimits": {"maxSizeBytes": 16}})

    result = asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))

    assert result.is_error is True
    assert "Notebook content" in result.content
    assert "exceeds maximum allowed size (16 B)" in result.content
    assert "jq '.cells[:20]'" in result.content
