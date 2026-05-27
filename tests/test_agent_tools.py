# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：test_agent_tools.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

import asyncio
import base64
import json
import os
import shutil
import shlex
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy, StaticToolPermissionPolicy, build_tool_permission_policy, describe_tool_impact
from agents.kernel.runtime import AgentResult, AgentRuntime, AgentSession, ScriptedModelClient
from agents.kernel.schema import Message, ModelResponse, RuntimeEvent, ToolCall
from agents.kernel.hooks import InMemoryHookStore
from agents.kernel.session_state import InMemorySessionStateStore
from agents.kernel.capabilities.memory import InMemoryMemoryStore, MemoryScope
from agents.kernel.capabilities.skills import SkillLoader, SkillRegistry
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.sandbox.types import SandboxCommandResult
import agents.kernel.capabilities.tools.builtin.filesystem_media as filesystem_media
from agents.kernel.capabilities.tools.builtin.browser import browser_open
from agents.kernel.capabilities.tools.builtin.shell import classify_shell_command, detect_blocked_sleep_pattern, is_silent_shell_command
from agents.kernel.capabilities.tools.builtin.worktree import restore_active_worktree_session
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolDefinition, ToolExecutionError, ToolRegistry
from agents.kernel.specs import AgentSpec
from agents.kernel.state import InMemoryAgentProfileStore, InMemoryArtifactStore, LocalArtifactBlobStore
from agents.kernel.tasks import InMemoryScheduleStore, InMemoryTaskStore, TaskEngine, TaskStatus, TaskStepStatus
from agents.kernel.teams import InMemoryTeamStore


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )


def test_tool_registry_registers_specs_and_rejects_duplicates():
    registry = ToolRegistry()
    registry.register(
        "echo",
        "Echo text",
        {"type": "object", "properties": {"text": {"type": "string"}}},
        lambda text: text,
    )

    assert registry.specs()[0].name == "echo"
    with pytest.raises(ValueError):
        registry.register("echo", "Echo again", {}, lambda: "x")


def test_tool_registry_exposes_metadata_in_specs():
    registry = ToolRegistry()
    registry.register("dangerous", "Dangerous", {}, lambda: "ok", metadata={"risk": "high"})

    spec = registry.specs(["dangerous"])[0]

    assert spec.raw["metadata"]["risk"] == "high"


def test_builtin_coding_tools_expose_contract_metadata(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True, allow_network=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    metadata = {
        spec.name: spec.raw["metadata"]
        for spec in registry.specs(
            [
                "filesystem.read",
                "filesystem.write",
                "notebook.edit",
                "lsp.query",
                "search.glob",
                "shell.run",
                "shell.output",
                "shell.kill",
                "sleep.wait",
                "config.manage",
                "user.ask",
                "user.message",
                "worktree.enter",
                "worktree.exit",
            ]
        )
    }

    assert metadata["filesystem.read"]["read_only"] is True
    assert metadata["filesystem.read"]["path_parameters"] == ["path"]
    assert metadata["filesystem.read"]["activity"] == {
        "kind": "workspace",
        "title": "Read file",
        "target_argument": "path",
    }
    assert metadata["filesystem.write"]["writes_state"] is True
    assert metadata["filesystem.write"]["concurrency_safe"] is False
    assert metadata["filesystem.write"]["activity"]["kind"] == "edit"
    assert metadata["notebook.edit"]["writes_state"] is True
    assert metadata["notebook.edit"]["concurrency_safe"] is False
    assert metadata["notebook.edit"]["path_parameters"] == ["notebook_path"]
    assert metadata["notebook.edit"]["src_origin_tool"] == "NotebookEdit"
    assert metadata["notebook.edit"]["activity"] == {
        "kind": "edit",
        "title": "Edit notebook",
        "target_argument": "notebook_path",
    }
    assert metadata["lsp.query"]["read_only"] is True
    assert metadata["lsp.query"]["path_parameters"] == ["filePath"]
    assert metadata["lsp.query"]["activity"] == {
        "kind": "workspace",
        "title": "Query language server",
        "target_argument": "filePath",
    }
    assert metadata["search.glob"]["read_only"] is True
    assert metadata["search.glob"]["path_parameters"] == ["path"]
    assert metadata["search.glob"]["activity"] == {
        "kind": "workspace",
        "title": "Find files",
        "target_argument": "pattern",
    }
    assert metadata["shell.run"]["concurrency_safe"] is False
    assert metadata["shell.run"]["cancels_siblings_on_error"] is True
    assert metadata["shell.run"]["interrupt_behavior"] == "cancel"
    assert metadata["shell.run"]["activity"] == {
        "kind": "terminal",
        "title": "Run shell command",
        "target_argument": "command",
    }
    assert metadata["shell.output"]["read_only"] is True
    assert metadata["shell.output"]["activity"]["title"] == "Read background shell output"
    assert metadata["shell.kill"]["writes_state"] is True
    assert metadata["sleep.wait"]["read_only"] is True
    assert metadata["sleep.wait"]["interrupt_behavior"] == "cancel"
    assert metadata["sleep.wait"]["activity"] == {
        "kind": "wait",
        "title": "Wait",
        "target_argument": "duration_seconds",
    }
    assert metadata["config.manage"]["writes_state"] is True
    assert metadata["config.manage"]["activity"] == {
        "kind": "state",
        "title": "Manage config",
        "target_argument": "setting",
    }
    assert metadata["user.ask"]["read_only"] is True
    assert metadata["user.ask"]["requires_user_interaction"] is True
    assert metadata["user.message"]["read_only"] is True
    assert metadata["user.message"]["user_visible"] is True
    assert metadata["worktree.enter"]["writes_state"] is True
    assert metadata["worktree.enter"]["activity"] == {
        "kind": "state",
        "title": "Enter worktree",
        "target_argument": "name",
    }
    assert metadata["worktree.exit"]["writes_state"] is True
    assert metadata["worktree.exit"]["destructive"] is True


def test_tool_registry_describes_call_activity_target_and_paths(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    write = registry.describe_call("filesystem.write", {"path": "src/app.py", "content": "print('ok')"})
    notebook = registry.describe_call("notebook.edit", {"notebook_path": "analysis.ipynb", "cell_id": "cell-0", "new_source": "x = 1"})
    glob = registry.describe_call("search.glob", {"pattern": "**/*.py", "path": "src"})
    shell = registry.describe_call("shell.run", {"command": "pytest -q"})

    assert write["activity"]["kind"] == "edit"
    assert write["target"] == "src/app.py"
    assert write["paths"] == ["src/app.py"]
    assert write["metadata"]["writes_state"] is True
    assert notebook["activity"]["kind"] == "edit"
    assert notebook["target"] == "analysis.ipynb"
    assert notebook["paths"] == ["analysis.ipynb"]
    assert glob["activity"]["kind"] == "workspace"
    assert glob["target"] == "**/*.py"
    assert glob["paths"] == ["src"]
    assert shell["activity"]["kind"] == "terminal"
    assert shell["target"] == "pytest -q"
    assert shell["paths"] == []


def test_src_origin_alias_tools_execute_against_canonical_implementations(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("hello\nneedle\n", encoding="utf-8")
    notebook = {
        "cells": [{"cell_type": "markdown", "id": "intro", "source": "# Title\n", "metadata": {}}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allowed_commands=("echo",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    alias_specs = {
        spec.name: spec
        for spec in registry.specs(
            [
                "Read",
                "Write",
                "Edit",
                "MultiEdit",
                "Bash",
                "TaskOutput",
                "BashOutputTool",
                "TaskStop",
                "KillShell",
                "Glob",
                "Grep",
                "TodoWrite",
                "NotebookEdit",
                "LSP",
                "Sleep",
                "EnterWorktree",
                "ExitWorktree",
            ]
        )
    }
    read = asyncio.run(registry.execute("Read", {"file_path": "notes.txt"}))
    written = asyncio.run(registry.execute("Write", {"file_path": "draft.txt", "content": "alpha\nsecond\n"}))
    edited = asyncio.run(
        registry.execute("Edit", {"file_path": "draft.txt", "old_string": "alpha\n", "new_string": "beta\n"})
    )
    multi_edited = asyncio.run(
        registry.execute(
            "MultiEdit",
            {
                "file_path": "draft.txt",
                "edits": [
                    {"old_string": "beta", "new_string": "gamma"},
                    {"old_string": "second", "new_string": "third"},
                ],
            },
        )
    )
    globbed = asyncio.run(registry.execute("Glob", {"pattern": "*.txt", "path": "."}))
    grepped = asyncio.run(registry.execute("Grep", {"pattern": "needle", "path": ".", "output_mode": "content"}))
    bashed = asyncio.run(registry.execute("Bash", {"command": "echo ok"}))
    async def run_background_alias():
        backgrounded_result = await registry.execute("Bash", {"command": "echo later", "run_in_background": True})
        output_result = await registry.execute(
            "BashOutputTool", {"task_id": backgrounded_result.raw["backgroundTaskId"], "block": True}
        )
        invalid_output = await registry.execute(
            "BashOutputTool", {"task_id": backgrounded_result.raw["backgroundTaskId"], "max_bytes": 10}
        )
        return backgrounded_result, output_result, invalid_output

    backgrounded, bash_output, bad_bash_output = asyncio.run(run_background_alias())
    todos = asyncio.run(
        registry.execute(
            "TodoWrite",
            {"todos": [{"content": "Check aliases", "status": "in_progress", "activeForm": "Checking aliases"}]},
        )
    )
    slept = asyncio.run(registry.execute("Sleep", {"duration_seconds": 0.01, "reason": "alias test"}))
    asyncio.run(registry.execute("Read", {"file_path": "analysis.ipynb"}))
    notebook_edit = asyncio.run(
        registry.execute(
            "NotebookEdit",
            {"notebook_path": "analysis.ipynb", "cell_id": "intro", "new_source": "Updated title\n"},
        )
    )
    lsp = asyncio.run(registry.execute("LSP", {"operation": "hover", "filePath": "notes.txt", "line": 1, "character": 1}))

    assert alias_specs["Read"].raw["metadata"]["alias_of"] == "filesystem.read"
    assert alias_specs["Edit"].raw["metadata"]["alias_of"] == "patch.apply"
    assert alias_specs["MultiEdit"].raw["metadata"]["alias_of"] == "patch.apply"
    assert alias_specs["Bash"].raw["metadata"]["alias_of"] == "shell.run"
    assert alias_specs["BashOutputTool"].raw["metadata"]["alias_of"] == "shell.output"
    assert alias_specs["TaskOutput"].raw["metadata"]["defer"] is True
    assert alias_specs["BashOutputTool"].raw["metadata"]["defer"] is True
    assert alias_specs["TaskStop"].raw["metadata"]["defer"] is True
    assert alias_specs["KillShell"].raw["metadata"]["defer"] is True
    assert alias_specs["TodoWrite"].raw["metadata"]["defer"] is True
    assert alias_specs["NotebookEdit"].raw["metadata"]["alias_of"] == "notebook.edit"
    assert alias_specs["LSP"].raw["metadata"]["alias_of"] == "lsp.query"
    assert alias_specs["EnterWorktree"].raw["metadata"]["alias_of"] == "worktree.enter"
    assert alias_specs["ExitWorktree"].raw["metadata"]["alias_of"] == "worktree.exit"
    assert read.is_error is False
    assert read.raw["type"] == "text"
    assert read.raw["file"]["filePath"] == "notes.txt"
    assert written.is_error is False
    assert written.raw["path"] == "draft.txt"
    assert edited.is_error is False
    assert edited.raw["filePath"] == "draft.txt"
    assert multi_edited.is_error is False
    assert multi_edited.content == "The file draft.txt has been updated successfully. 2 edits applied."
    assert multi_edited.raw["files"][0]["path"] == "draft.txt"
    assert (tmp_path / "draft.txt").read_text(encoding="utf-8") == "gamma\nthird\n"
    assert "draft.txt" in globbed.raw["filenames"]
    assert grepped.content == "notes.txt:2:needle"
    assert bashed.raw["stdout"] == "ok\n"
    assert bash_output.raw["retrieval_status"] == "success"
    assert bash_output.raw["task"]["task_type"] == "local_bash"
    assert bash_output.raw["task"]["output"].strip() == "later"
    assert bad_bash_output.is_error is True
    assert bad_bash_output.raw["details"] == "unexpected argument: max_bytes"
    assert context.todos[0]["content"] == "Check aliases"
    assert todos.content == (
        "Todos have been modified successfully. "
        "Ensure that you continue to use the todo list to track your progress. "
        "Please proceed with the current tasks if applicable"
    )
    assert todos.raw["newTodos"][0]["activeForm"] == "Checking aliases"
    assert slept.raw["reason"] == "alias test"
    assert notebook_edit.is_error is False
    assert notebook_edit.raw["cell_id"] == "intro"
    assert json.loads((tmp_path / "analysis.ipynb").read_text(encoding="utf-8"))["cells"][0]["source"] == "Updated title\n"
    assert lsp.is_error is False
    assert lsp.content == "No LSP server available for file type: .txt"
    assert lsp.raw["operation"] == "hover"
    assert lsp.raw["filePath"] == "notes.txt"

    impact = describe_tool_impact(
        ToolCall(
            id="call-edit",
            name="Edit",
            arguments={"file_path": "draft.txt", "old_string": "beta\n", "new_string": "gamma\n"},
        )
    )
    assert impact.risk == "medium"
    assert impact.operations == ["file_patch"]
    assert impact.paths == ["draft.txt"]

    multi_impact = describe_tool_impact(
        ToolCall(
            id="call-multi-edit",
            name="MultiEdit",
            arguments={
                "file_path": "draft.txt",
                "edits": [{"old_string": "third", "new_string": "fourth"}],
            },
        )
    )
    assert multi_impact.risk == "medium"
    assert multi_impact.operations == ["file_patch"]
    assert multi_impact.paths == ["draft.txt"]

    lsp_impact = describe_tool_impact(
        ToolCall(id="call-lsp", name="LSP", arguments={"operation": "hover", "filePath": "notes.txt", "line": 1, "character": 1})
    )
    assert lsp_impact.risk == "low"
    assert lsp_impact.operations == ["file_read", "lsp_query"]
    assert lsp_impact.paths == ["notes.txt"]


class _FakeLspProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def query(
        self,
        *,
        operation: str,
        filePath: str,
        absolute_path: Path,
        line: int,
        character: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "operation": operation,
                "filePath": filePath,
                "absolute_path": absolute_path,
                "line": line,
                "character": character,
            }
        )
        return {"result": "Hover info", "resultCount": 1, "fileCount": 1}


class _FakeLspNotificationProvider:
    def __init__(self) -> None:
        self.events: list[tuple[str, object, object, object]] = []

    def clear_diagnostics(self, *, file_uri: str) -> None:
        self.events.append(("clear", file_uri, "", ""))

    def change_file(self, *, file_path: str, absolute_path: Path, content: str) -> None:
        self.events.append(("change", file_path, absolute_path, content))

    def save_file(self, *, file_path: str, absolute_path: Path) -> None:
        self.events.append(("save", file_path, absolute_path, ""))


def test_lsp_tool_uses_context_provider(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def app():\n    return 1\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    provider = _FakeLspProvider()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        lsp_provider=provider,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute("lsp.query", {"operation": "hover", "filePath": "src/app.py", "line": 1, "character": 5})
    )

    assert result.is_error is False
    assert result.content == "Hover info"
    assert result.raw["operation"] == "hover"
    assert result.raw["filePath"] == "src/app.py"
    assert result.raw["resultCount"] == 1
    assert result.raw["fileCount"] == 1
    assert provider.calls == [
        {
            "operation": "hover",
            "filePath": "src/app.py",
            "absolute_path": (tmp_path / "src" / "app.py").resolve(),
            "line": 1,
            "character": 5,
        }
    ]


def test_lsp_tool_validates_src_origin_path_guards(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "large.py").write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    missing = asyncio.run(
        registry.execute("LSP", {"operation": "hover", "filePath": "missing.py", "line": 1, "character": 1})
    )
    directory = asyncio.run(
        registry.execute("LSP", {"operation": "hover", "filePath": "src", "line": 1, "character": 1})
    )
    bad_line = asyncio.run(
        registry.execute("LSP", {"operation": "hover", "filePath": "missing.py", "line": 0, "character": 1})
    )
    large = asyncio.run(
        registry.execute("LSP", {"operation": "hover", "filePath": "large.py", "line": 1, "character": 1})
    )

    assert missing.is_error is True
    assert missing.content == "File does not exist: missing.py"
    assert directory.is_error is True
    assert directory.content == "Path is not a file: src"
    assert bad_line.is_error is True
    assert bad_line.content == "line must be a positive integer"
    assert large.is_error is False
    assert large.content == "File too large for LSP analysis (11MB exceeds 10MB limit)"


def test_file_write_and_patch_notify_lsp_provider_after_success(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "edit.py").write_text("value = 1\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    provider = _FakeLspNotificationProvider()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        lsp_provider=provider,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    written = asyncio.run(registry.execute("filesystem.write", {"path": "created.py", "content": "print(1)\n"}))
    asyncio.run(registry.execute("filesystem.read", {"path": "edit.py"}))
    patched = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "edit.py", "old_text": "value = 1\n", "new_text": "value = 2\n"}]},
        )
    )

    assert written.is_error is False
    assert patched.is_error is False
    assert provider.events == [
        ("clear", "file://%s" % (tmp_path / "created.py").resolve(), "", ""),
        ("change", "created.py", (tmp_path / "created.py").resolve(), "print(1)\n"),
        ("save", "created.py", (tmp_path / "created.py").resolve(), ""),
        ("clear", "file://%s" % (tmp_path / "edit.py").resolve(), "", ""),
        ("change", "edit.py", (tmp_path / "edit.py").resolve(), "value = 2\n"),
        ("save", "edit.py", (tmp_path / "edit.py").resolve(), ""),
    ]


def test_notebook_edit_notifies_lsp_provider_after_success(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "id": "calc",
                "source": "print(1)\n",
                "outputs": [{"output_type": "stream", "text": "1\n"}],
                "execution_count": 7,
                "metadata": {},
            },
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    provider = _FakeLspNotificationProvider()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        lsp_provider=provider,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    edited = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "calc", "new_source": "print(2)\n"},
        )
    )

    assert edited.is_error is False
    assert provider.events == [
        ("clear", "file://%s" % (tmp_path / "analysis.ipynb").resolve(), "", ""),
        ("change", "analysis.ipynb", (tmp_path / "analysis.ipynb").resolve(), edited.raw["updated_file"]),
        ("save", "analysis.ipynb", (tmp_path / "analysis.ipynb").resolve(), ""),
    ]


def test_config_manage_and_src_origin_alias_update_session_config(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
        agent_spec=AgentSpec.from_overrides(protocol="openai-chat", model="base-model", permission_profile="auto"),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    theme = asyncio.run(registry.execute("Config", {"setting": "theme"}))
    verbose = asyncio.run(registry.execute("Config", {"setting": "verbose", "value": "true"}))
    model = asyncio.run(registry.execute("config.manage", {"setting": "model", "value": "override-model"}))
    permission = asyncio.run(registry.execute("Config", {"setting": "permissions.defaultMode", "value": "plan"}))
    invalid = asyncio.run(registry.execute("Config", {"setting": "editorMode", "value": "emacs"}))
    missing = asyncio.run(registry.execute("Config", {"setting": "missing.setting"}))
    record = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))

    assert theme.content == 'theme = "dark"'
    assert verbose.raw["newValue"] is True
    assert model.raw["newValue"] == "override-model"
    assert context.agent_spec.model.model == "override-model"
    assert permission.raw["newValue"] == "plan"
    assert context.permission_profile_override == "plan"
    assert context.permission_mode_override == "ask"
    assert invalid.is_error is True
    assert invalid.raw["error"] == 'Invalid value "emacs". Options: normal, vim'
    assert missing.is_error is True
    assert missing.raw["error"] == 'Unknown setting: "missing.setting"'
    assert record.metadata["config.verbose"] == "true"
    assert record.metadata["config.model"] == json.dumps("override-model")
    assert record.metadata["config.permissions.defaultMode"] == json.dumps("plan")

    specs = {spec.name: spec.raw["metadata"]["alias_of"] for spec in registry.specs(["Config"])}
    assert specs == {"Config": "config.manage"}

    read_impact = describe_tool_impact(ToolCall(id="call-config-read", name="Config", arguments={"setting": "model"}))
    write_impact = describe_tool_impact(
        ToolCall(id="call-config-write", name="Config", arguments={"setting": "model", "value": "override-model"})
    )
    read_decision = asyncio.run(
        build_tool_permission_policy(AgentSpec()).authorize(ToolCall(id="read", name="Config", arguments={"setting": "model"}))
    )
    write_decision = asyncio.run(
        build_tool_permission_policy(AgentSpec()).authorize(
            ToolCall(id="write", name="Config", arguments={"setting": "model", "value": "override-model"})
        )
    )

    assert read_impact.operations == ["config_read"]
    assert write_impact.operations == ["config_write"]
    assert read_decision.allowed is True
    assert write_decision.requires_approval is True


def test_exit_worktree_noops_without_active_session(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    kept = asyncio.run(registry.execute("ExitWorktree", {"action": "keep"}))
    removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove", "discard_changes": True}))

    for result, action in ((kept, "keep"), (removed, "remove")):
        assert result.is_error is False
        assert result.raw["action"] == action
        assert result.raw["noop"] is True
        assert result.raw["reason"] == "no_active_worktree_session"
        assert result.raw["originalCwd"] == str(tmp_path.resolve())
        assert result.raw["worktreePath"] == ""
        assert result.raw["worktreeBranch"] == ""
        assert "No filesystem changes were made." in result.content

    assert context.workspace.path == tmp_path.resolve()
    assert context.active_worktree_session == {}


def test_worktree_tools_enter_keep_resume_and_remove_git_worktrees(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")

    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("EnterWorktree", {"name": "feature/test"}))
    worktree_path = Path(entered.raw["worktreePath"])
    record_after_enter = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    assert record_after_enter is not None
    restored_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
    )
    restored = restore_active_worktree_session(restored_context, record_after_enter.active_worktree_session)
    kept = asyncio.run(registry.execute("ExitWorktree", {"action": "keep"}))
    record_after_keep = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    kept_path_exists = worktree_path.exists()
    resumed = asyncio.run(registry.execute("worktree.enter", {"name": "feature/test"}))
    clean_removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))
    dirty_entered = asyncio.run(registry.execute("worktree.enter", {"name": "cleanup"}))
    dirty_path = Path(dirty_entered.raw["worktreePath"])
    (dirty_path / "README.md").write_text("dirty\n", encoding="utf-8")
    blocked = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))
    blocked_workspace = context.workspace.path
    removed = asyncio.run(registry.execute("ExitWorktree", {"action": "remove", "discard_changes": True}))
    record_after_remove = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    enter_impact = describe_tool_impact(ToolCall(id="enter-wt", name="EnterWorktree", arguments={"name": "cleanup"}))
    remove_impact = describe_tool_impact(ToolCall(id="exit-wt", name="ExitWorktree", arguments={"action": "remove"}))
    remove_decision = asyncio.run(
        build_tool_permission_policy(AgentSpec()).authorize(ToolCall(id="remove", name="ExitWorktree", arguments={"action": "remove"}))
    )

    assert entered.is_error is False
    assert entered.raw["worktreeBranch"] == "worktree-feature+test"
    assert record_after_enter is not None
    assert record_after_enter.active_worktree_session["worktreePath"] == str(worktree_path)
    assert restored is True
    assert restored_context.workspace.path == worktree_path.resolve()
    assert kept.raw["action"] == "keep"
    assert record_after_keep.active_worktree_session == {}
    assert context.workspace.path == repo.resolve()
    assert kept_path_exists is True
    assert resumed.raw["resumed"] is True
    assert clean_removed.is_error is False
    assert not worktree_path.exists()
    assert dirty_entered.is_error is False
    assert blocked.is_error is True
    assert "discard_changes=true" in blocked.content
    assert blocked_workspace == dirty_path.resolve()
    assert removed.is_error is False
    assert removed.raw["discardedFiles"] == 1
    assert record_after_remove.active_worktree_session == {}
    assert not dirty_path.exists()
    assert context.workspace.path == repo.resolve()
    assert context.active_worktree_session == {}
    assert enter_impact.operations == ["worktree_create", "workspace_switch"]
    assert remove_impact.risk == "high"
    assert remove_decision.requires_approval is True


def test_worktree_enter_can_create_from_github_pr_reference(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    origin = tmp_path / "origin.git"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    _run_git(tmp_path, "init", "--bare", str(origin))
    branch = _run_git(repo, "branch", "--show-current").stdout.strip()
    _run_git(repo, "remote", "add", "origin", str(origin))
    _run_git(repo, "push", "origin", "HEAD:refs/heads/%s" % branch)
    _run_git(repo, "checkout", "-b", "feature/pr-123")
    (repo / "README.md").write_text("from pr\n", encoding="utf-8")
    _run_git(repo, "commit", "-am", "pr change")
    _run_git(repo, "push", "origin", "HEAD:refs/pull/123/head")
    _run_git(repo, "checkout", branch)

    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=repo,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    url_entered = asyncio.run(
        registry.execute("worktree.enter", {"name": "https://github.com/acme/repo/pull/123?view=files"})
    )
    url_worktree_path = Path(url_entered.raw["worktreePath"])
    url_content = (url_worktree_path / "README.md").read_text(encoding="utf-8")
    url_removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))
    camel_entered = asyncio.run(registry.execute("EnterWorktree", {"prNumber": 123}))
    camel_worktree_path = Path(camel_entered.raw["worktreePath"])
    camel_content = (camel_worktree_path / "README.md").read_text(encoding="utf-8")
    camel_removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))
    conflict = asyncio.run(registry.execute("worktree.enter", {"name": "#123", "prNumber": 456}))

    assert url_entered.is_error is False
    assert url_entered.raw["worktreeBranch"] == "worktree-pr-123"
    assert url_entered.raw["prNumber"] == 123
    assert url_entered.raw["baseRef"] == "FETCH_HEAD"
    assert url_content == "from pr\n"
    assert url_removed.is_error is False
    assert not url_worktree_path.exists()
    assert camel_entered.is_error is False
    assert camel_entered.raw["worktreeBranch"] == "worktree-pr-123"
    assert camel_entered.raw["prNumber"] == 123
    assert camel_content == "from pr\n"
    assert camel_removed.is_error is False
    assert not camel_worktree_path.exists()
    assert conflict.is_error is True
    assert "Conflicting pull request references" in conflict.content


def test_worktree_enter_runs_src_origin_style_post_creation_setup(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    (repo / ".gitignore").write_text(".env\nconfig/local.toml\nignored/\ncache/\n", encoding="utf-8")
    (repo / ".worktreeinclude").write_text("ignored/secret.txt\nignored/nested/\n", encoding="utf-8")
    (repo / ".husky").mkdir()
    (repo / ".husky" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git(repo, "add", ".gitignore", ".worktreeinclude", ".husky/pre-commit", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    (repo / ".env").write_text("TOKEN=local\n", encoding="utf-8")
    (repo / "config").mkdir()
    (repo / "config" / "local.toml").write_text("[local]\nvalue = true\n", encoding="utf-8")
    (repo / "ignored" / "nested").mkdir(parents=True)
    (repo / "ignored" / "secret.txt").write_text("secret\n", encoding="utf-8")
    (repo / "ignored" / "nested" / "deep.txt").write_text("deep\n", encoding="utf-8")
    (repo / "cache").mkdir()
    (repo / "cache" / "artifact.bin").write_text("cache\n", encoding="utf-8")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=repo,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True),
        agent_spec=AgentSpec(metadata={"worktree": {"symlink_directories": ["cache"]}}),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("worktree.enter", {"name": "post-create"}))
    worktree_path = Path(entered.raw["worktreePath"])
    hooks_path = _run_git(worktree_path, "config", "core.hooksPath").stdout.strip()
    status = _run_git(repo, "status", "--porcelain", "--untracked-files=all").stdout
    env_content = (worktree_path / ".env").read_text(encoding="utf-8")
    local_config_content = (worktree_path / "config" / "local.toml").read_text(encoding="utf-8")
    secret_content = (worktree_path / "ignored" / "secret.txt").read_text(encoding="utf-8")
    deep_content = (worktree_path / "ignored" / "nested" / "deep.txt").read_text(encoding="utf-8")
    cache_is_symlink = (worktree_path / "cache").is_symlink()
    cache_target = (worktree_path / "cache").resolve()
    removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove", "discard_changes": True}))

    assert entered.is_error is False
    assert sorted(entered.raw["copiedFiles"]) == ["ignored/nested/deep.txt", "ignored/secret.txt"]
    assert sorted(entered.raw["copiedLocalFiles"]) == [".env", "config/local.toml"]
    assert entered.raw["symlinkedDirectories"] == ["cache"]
    assert entered.raw["hooksPath"] == str((repo / ".husky").resolve())
    assert hooks_path == str((repo / ".husky").resolve())
    assert env_content == "TOKEN=local\n"
    assert local_config_content == "[local]\nvalue = true\n"
    assert secret_content == "secret\n"
    assert deep_content == "deep\n"
    assert cache_is_symlink is True
    assert cache_target == (repo / "cache").resolve()
    assert ".agents/worktrees/" in (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".agents/worktrees" not in status
    assert removed.is_error is False


def test_worktree_enter_applies_sparse_paths_from_agent_metadata(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _run_git(repo, "add", "src/app.py", "docs/guide.md")
    _run_git(repo, "commit", "-m", "initial")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=repo,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True),
        agent_spec=AgentSpec(metadata={"worktree": {"sparse_paths": ["src"]}}),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("EnterWorktree", {"name": "sparse"}))
    worktree_path = Path(entered.raw["worktreePath"])
    src_exists = (worktree_path / "src" / "app.py").is_file()
    docs_exists = (worktree_path / "docs" / "guide.md").exists()
    removed = asyncio.run(registry.execute("ExitWorktree", {"action": "remove"}))

    assert entered.is_error is False
    assert entered.raw["usedSparsePaths"] is True
    assert src_exists is True
    assert docs_exists is False
    assert context.active_worktree_session == {}
    assert removed.is_error is False


def test_ask_user_question_tool_and_src_origin_alias(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    questions = [
        {
            "question": "Which auth method should we use?",
            "header": "Auth",
            "options": [
                {"label": "OAuth (Recommended)", "description": "Use OAuth login."},
                {"label": "JWT", "description": "Use signed tokens."},
            ],
        }
    ]

    answered = asyncio.run(
        registry.execute(
            "AskUserQuestion",
            {
                "questions": questions,
                "answers": {"Which auth method should we use?": "OAuth (Recommended)"},
                "annotations": {"Which auth method should we use?": {"notes": "Matches product direction."}},
            },
        )
    )
    invalid = asyncio.run(registry.execute("AskUserQuestion", {"questions": [{**questions[0], "options": questions[0]["options"][:1]}]}))

    assert answered.is_error is False
    assert answered.raw["answers"] == {"Which auth method should we use?": "OAuth (Recommended)"}
    assert "User answered questions" in answered.content
    assert invalid.is_error is True
    assert "must include 2-4 options" in invalid.content
    assert registry.specs(["AskUserQuestion"])[0].raw["metadata"]["alias_of"] == "user.ask"

    impact = describe_tool_impact(ToolCall(id="call-ask", name="AskUserQuestion", arguments={"questions": questions}))
    decision = asyncio.run(
        build_tool_permission_policy(AgentSpec()).authorize(ToolCall(id="ask", name="AskUserQuestion", arguments={"questions": questions}))
    )

    assert impact.operations == ["user_interaction"]
    assert impact.query == "Which auth method should we use?"
    assert decision.requires_approval is True
    assert decision.metadata["permission"] == "user_interaction"


def test_send_user_message_and_brief_aliases_attach_workspace_files(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "report.txt").write_text("done\n", encoding="utf-8")
    (tmp_path / "pixel.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    sent = asyncio.run(
        registry.execute(
            "SendUserMessage",
            {"message": "Review complete.", "attachments": ["report.txt", "pixel.png"], "status": "normal"},
        )
    )
    brief = asyncio.run(registry.execute("Brief", {"message": "Heads up.", "status": "proactive"}))
    missing = asyncio.run(registry.execute("SendUserMessage", {"message": "Missing file.", "attachments": ["missing.txt"], "status": "normal"}))

    assert sent.is_error is False
    assert sent.content == "Message delivered to user. (2 attachments included)"
    assert sent.raw["message"] == "Review complete."
    assert sent.raw["status"] == "normal"
    assert sent.raw["attachments"] == [
        {"path": "report.txt", "size": 5, "isImage": False},
        {"path": "pixel.png", "size": 8, "isImage": True},
    ]
    assert brief.raw["status"] == "proactive"
    assert "sentAt" in brief.raw
    assert missing.is_error is True
    assert "attachment not found" in missing.content

    aliases = {spec.name: spec.raw["metadata"]["alias_of"] for spec in registry.specs(["SendUserMessage", "Brief"])}
    assert aliases == {"SendUserMessage": "user.message", "Brief": "user.message"}

    impact = describe_tool_impact(
        ToolCall(
            id="call-message",
            name="SendUserMessage",
            arguments={"message": "Review complete.", "attachments": ["report.txt"]},
        )
    )
    assert impact.operations == ["user_message"]
    assert impact.paths == ["report.txt"]
    assert impact.query == "Review complete."


def test_builtin_search_glob_finds_workspace_files(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (tmp_path / "src" / "view.tsx").write_text("export {}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("search.glob", {"pattern": "*.{py,tsx}", "path": "src"}))
    limited = asyncio.run(registry.execute("search.glob", {"pattern": "*.{py,tsx}", "path": "src", "max_results": 1}))
    empty = asyncio.run(registry.execute("search.glob", {"pattern": "*.go", "path": "src"}))
    impact = describe_tool_impact(ToolCall(id="call-glob", name="search.glob", arguments={"pattern": "*.{py,tsx}", "path": "src"}))

    assert result.is_error is False
    assert sorted(result.raw["filenames"]) == ["src/app.py", "src/view.tsx"]
    assert sorted(result.content.splitlines()) == ["src/app.py", "src/view.tsx"]
    assert result.raw["numFiles"] == 2
    assert "durationMs" in result.raw
    assert len(limited.raw["filenames"]) == 1
    assert limited.raw["truncated"] is True
    assert limited.content.endswith("(Results are truncated. Consider using a more specific path or pattern.)")
    assert empty.content == "No files found"
    assert impact.operations == ["file_read"]
    assert impact.paths == ["src"]
    assert impact.query == "*.{py,tsx}"


def test_builtin_search_grep_formats_model_visible_results(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("alpha\nneedle\n", encoding="utf-8")
    (tmp_path / "src" / "view.tsx").write_text("needle\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    default = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src"}))
    content = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src", "output_mode": "content"}))
    count = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src", "output_mode": "count"}))
    filtered = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src", "glob": "*.py"}))
    typed = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src", "type": "py"}))
    limited = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "src", "head_limit": 1}))
    context = asyncio.run(
        registry.execute("search.grep", {"pattern": "needle", "path": "src", "output_mode": "content", "context": 1})
    )
    multiline = asyncio.run(
        registry.execute(
            "search.grep",
            {"pattern": "alpha\\nneedle", "path": "src", "output_mode": "content", "multiline": True},
        )
    )
    without_lines = asyncio.run(
        registry.execute(
            "search.grep",
            {"pattern": "needle", "path": "src", "glob": "*.py", "output_mode": "content", "-n": False},
        )
    )
    empty = asyncio.run(registry.execute("search.grep", {"pattern": "missing", "path": "src"}))

    assert default.is_error is False
    assert default.content.splitlines()[0] == "Found 2 files"
    assert default.content.splitlines()[1:] == ["src/app.py", "src/view.tsx"]
    assert default.raw["numFiles"] == 2
    assert default.raw["numMatches"] == 2
    assert default.raw["matches"][0]["line"] == "needle"
    assert content.content == "src/app.py:2:needle\nsrc/view.tsx:1:needle"
    assert content.raw["mode"] == "content"
    assert count.content.endswith("Found 2 total occurrences across 2 files.")
    assert "src/app.py:1" in count.content
    assert filtered.content == "Found 1 file\nsrc/app.py"
    assert filtered.raw["glob"] == "*.py"
    assert filtered.raw["filenames"] == ["src/app.py"]
    assert typed.content == "Found 1 file\nsrc/app.py"
    assert typed.raw["type"] == "py"
    assert limited.content == "Found 1 file limit: 1\nsrc/app.py"
    assert limited.raw["appliedLimit"] == 1
    assert context.content == "src/app.py-1-alpha\nsrc/app.py:2:needle\nsrc/view.tsx:1:needle"
    assert context.raw["numLines"] == 3
    assert context.raw["matches"][0]["is_match"] is False
    assert multiline.content == "src/app.py:1:alpha\nsrc/app.py-2-needle"
    assert multiline.raw["multiline"] is True
    assert without_lines.content == "src/app.py:needle"
    assert empty.content == "No files found"


def test_shell_run_accepts_src_origin_timeout_alias_and_description(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    script = "print('ok')"
    result = asyncio.run(
        registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "timeout": 5000,
                "description": "Print ok",
            },
        )
    )

    assert result.is_error is False
    assert result.raw["stdout"] == "ok\n"
    assert result.raw["description"] == "Print ok"
    assert result.raw["background"] is False
    assert result.raw["interrupted"] is False
    assert result.raw["isImage"] is False
    assert result.raw["dangerouslyDisableSandbox"] is False
    assert result.raw["timeout_seconds"] == 5.0
    assert result.raw["timeout_ms"] == 5000


def test_shell_run_rejects_unsupported_sandbox_override(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=("echo",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("shell.run", {"command": "echo ok", "dangerouslyDisableSandbox": True}))

    assert result.is_error is True
    assert "dangerouslyDisableSandbox is not supported" in result.content
    assert result.raw["dangerouslyDisableSandbox"] is True
    assert result.raw["returnCodeInterpretation"] == "Sandbox override rejected"


def test_shell_run_background_returns_task_and_output_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout": 5000,
                "description": "Run short background script",
            },
        )
        task_id = started.raw["task_id"]
        not_ready = await registry.execute("shell.output", {"task_id": task_id, "block": False})
        final = await registry.execute("shell.output", {"task_id": task_id, "block": True, "timeout_seconds": 2.0})
        listed = await registry.execute("shell.backgrounds", {})
        return started, not_ready, final, listed

    started, not_ready, final, listed = asyncio.run(execute())

    assert started.is_error is False
    assert started.raw["background"] is True
    assert started.raw["backgroundTaskId"] == started.raw["task_id"]
    assert started.raw["backgroundedByUser"] is False
    assert started.raw["assistantAutoBackgrounded"] is False
    assert started.raw["interrupted"] is False
    assert started.raw["stdout"] == ""
    assert started.raw["stderr"] == ""
    assert started.raw["dangerouslyDisableSandbox"] is False
    assert started.raw["description"] == "Run short background script"
    assert started.raw["timeout_seconds"] == 5.0
    assert started.raw["timeout_ms"] == 5000
    assert started.raw["output_path"].startswith(".agents/task-output/shell_")
    assert not_ready.is_error is False
    assert not_ready.raw["retrieval_status"] in {"not_ready", "success"}
    assert final.is_error is False
    assert final.raw["retrieval_status"] == "success"
    assert final.raw["task"]["status"] == "completed"
    assert "start\ndone\n" in final.raw["output"]
    assert listed.raw["count"] == 1
    assert listed.raw["background_commands"][0]["task_id"] == started.raw["task_id"]
    assert (tmp_path / started.raw["output_path"]).read_text(encoding="utf-8") == "start\ndone\n"


def test_shell_output_truncates_without_file_read_full_read_error(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s"
                % (shlex.quote(sys.executable), shlex.quote("import sys; sys.stdout.write('0123456789abcdef')")),
                "run_in_background": True,
                "timeout": 5000,
                "description": "Emit long output",
            },
        )
        final = await registry.execute(
            "shell.output",
            {"task_id": started.raw["task_id"], "block": True, "timeout_seconds": 2.0, "max_bytes": 8},
        )
        return started, final

    started, final = asyncio.run(execute())

    assert started.is_error is False
    assert final.is_error is False
    assert final.raw["output"] == "01234567"
    assert final.raw["truncated"] is True


def test_shell_kill_stops_background_command(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(5)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout_seconds": 30.0,
            },
        )
        await asyncio.sleep(0.1)
        killed = await registry.execute("shell.kill", {"task_id": started.raw["task_id"]})
        output = await registry.execute("shell.output", {"task_id": started.raw["task_id"], "block": False})
        return started, killed, output

    started, killed, output = asyncio.run(execute())

    assert started.is_error is False
    assert killed.is_error is False
    assert killed.raw["killed"] is True
    assert killed.raw["task"]["status"] == "killed"
    assert output.raw["task"]["status"] == "killed"
    assert "start" in output.raw["output"]


def test_kill_shell_alias_returns_src_origin_stop_shape(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(5)"
        started = await registry.execute(
            "Bash",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout_seconds": 30.0,
            },
        )
        await asyncio.sleep(0.1)
        invalid = await registry.execute("KillShell", {"shell_id": started.raw["task_id"], "unused": True})
        killed = await registry.execute("KillShell", {"shell_id": started.raw["task_id"]})
        return started, invalid, killed

    started, invalid, killed = asyncio.run(execute())

    assert started.is_error is False
    assert invalid.is_error is True
    assert invalid.raw["details"] == "unexpected argument: unused"
    assert killed.is_error is False
    assert killed.raw["task_id"] == started.raw["task_id"]
    assert killed.raw["task_type"] == "local_bash"
    assert killed.raw["command"].startswith(shlex.quote(sys.executable))
    assert killed.raw["message"].startswith("Successfully stopped task: %s" % started.raw["task_id"])


def test_sleep_wait_is_dedicated_cancelable_wait_tool(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("sleep.wait", {"duration_seconds": 0.01, "reason": "test wait"}))
    impact = describe_tool_impact(ToolCall(id="call-sleep", name="sleep.wait", arguments={"duration_seconds": 2}))

    assert result.is_error is False
    assert result.raw["requested_seconds"] == 0.01
    assert result.raw["slept_seconds"] >= 0
    assert result.raw["reason"] == "test wait"
    assert result.raw["woke_for_notification"] is False
    assert impact.risk == "low"
    assert impact.operations == ["wait"]


def test_shell_run_blocks_long_foreground_sleep_in_favor_of_sleep_wait(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=("sleep",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    blocked = asyncio.run(registry.execute("shell.run", {"command": "sleep 2"}))

    assert blocked.is_error is True
    assert "Blocked: standalone sleep 2" in blocked.content
    assert "sleep.wait" in blocked.content
    assert detect_blocked_sleep_pattern("sleep 1") is None
    assert detect_blocked_sleep_pattern("sleep 0.5") is None
    assert detect_blocked_sleep_pattern("sleep 2 | cat") is None
    assert detect_blocked_sleep_pattern("sleep 2 && echo done") == "sleep 2 followed by: echo done"


def test_shell_run_reports_silent_command_and_failure_semantics(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=("mkdir", "false"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    silent = asyncio.run(registry.execute("shell.run", {"command": "mkdir created"}))
    failed = asyncio.run(registry.execute("shell.run", {"command": "false"}))

    assert silent.is_error is False
    assert silent.raw["exit_code"] == 0
    assert silent.raw["failed"] is False
    assert silent.raw["no_output_expected"] is True
    assert (tmp_path / "created").is_dir()
    assert failed.is_error is True
    assert failed.raw["exit_code"] != 0
    assert failed.raw["failed"] is True
    assert failed.raw["error"] == "tool_execution_error"
    assert failed.raw["return_code_interpretation"] == "Command failed with exit code 1"
    assert "Command failed with exit code 1" in failed.content
    assert is_silent_shell_command("mkdir a && touch b") is True
    assert is_silent_shell_command("mkdir a && echo done") is False


def test_shell_run_uses_src_origin_exit_code_semantics(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "hay.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "left.txt").write_text("left\n", encoding="utf-8")
    (tmp_path / "right.txt").write_text("right\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=("grep", "diff", "test"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    grep_no_matches = asyncio.run(registry.execute("shell.run", {"command": "grep needle hay.txt"}))
    diff_files = asyncio.run(registry.execute("shell.run", {"command": "diff left.txt right.txt"}))
    false_test = asyncio.run(registry.execute("shell.run", {"command": "test -f missing.txt"}))

    assert grep_no_matches.is_error is False
    assert grep_no_matches.raw["exit_code"] == 1
    assert grep_no_matches.raw["failed"] is False
    assert grep_no_matches.raw["return_code_interpretation"] == "No matches found"
    assert grep_no_matches.raw["returnCodeInterpretation"] == "No matches found"
    assert grep_no_matches.raw["noOutputExpected"] is False
    assert grep_no_matches.raw["commandClassification"] == {"isSearch": True, "isRead": False, "isList": False}
    assert diff_files.is_error is False
    assert diff_files.raw["exit_code"] == 1
    assert diff_files.raw["failed"] is False
    assert diff_files.raw["return_code_interpretation"] == "Files differ"
    assert diff_files.raw["returnCodeInterpretation"] == "Files differ"
    assert false_test.is_error is False
    assert false_test.raw["exit_code"] == 1
    assert false_test.raw["failed"] is False
    assert false_test.raw["return_code_interpretation"] == "Condition is false"
    assert classify_shell_command("cat hay.txt | jq .") == {"isSearch": False, "isRead": True, "isList": False}
    assert classify_shell_command('ls . && echo "---" && ls ..') == {"isSearch": False, "isRead": False, "isList": True}
    assert classify_shell_command("echo git status") == {"isSearch": False, "isRead": False, "isList": False}
    assert classify_shell_command("cat hay.txt | python -c 'print(1)'") == {"isSearch": False, "isRead": False, "isList": False}


def test_tool_execution_error_preserves_structured_raw_payload():
    registry = ToolRegistry()
    registry.register("structured.fail", "Structured failure", {}, lambda: (_ for _ in ()).throw(ToolExecutionError("bad output", raw={"code": 7})))

    result = asyncio.run(registry.execute("structured.fail", {}))

    assert result.is_error is True
    assert result.content == "bad output"
    assert result.raw == {"error": "tool_execution_error", "code": 7}


def test_tool_registry_accepts_tool_definitions_with_lifecycle_metadata():
    registry = ToolRegistry()
    registry.register_definition(
        ToolDefinition(
            name="inspect",
            description="Inspect state",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=lambda path: path,
            metadata={"risk": "low"},
            read_only=True,
            concurrency_safe=True,
            interrupt_behavior="cancel",
            max_result_size_chars=200,
        )
    )

    spec = registry.specs(["inspect"])[0]

    assert spec.raw["metadata"]["risk"] == "low"
    assert spec.raw["metadata"]["read_only"] is True
    assert spec.raw["metadata"]["interrupt_behavior"] == "cancel"
    assert spec.raw["metadata"]["max_result_size_chars"] == 200


def test_tool_registry_validates_json_schema_before_execution():
    registry = ToolRegistry()
    calls = []
    registry.register(
        "echo",
        "Echo text",
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        lambda text: calls.append(text) or text,
    )
    registry.register(
        "empty",
        "No arguments",
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        lambda: "empty",
    )

    missing = asyncio.run(registry.execute("echo", {}))
    wrong_type = asyncio.run(registry.execute("echo", {"text": 1}))
    extra = asyncio.run(registry.execute("echo", {"text": "ok", "unused": True}))
    empty_extra = asyncio.run(registry.execute("empty", {"unused": True}))
    ok = asyncio.run(registry.execute("echo", {"text": "ok"}))

    assert missing.is_error is True
    assert "missing required argument: text" in missing.content
    assert wrong_type.is_error is True
    assert "text must be string" in wrong_type.content
    assert extra.is_error is True
    assert "unexpected argument: unused" in extra.content
    assert empty_extra.is_error is True
    assert "unexpected argument: unused" in empty_extra.content
    assert ok.content == "ok"
    assert calls == ["ok"]


def test_tool_registry_can_disable_strict_input_validation():
    registry = ToolRegistry()
    registry.register(
        "loose",
        "Loose tool",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda **kwargs: kwargs,
        metadata={"strict_input_schema": False},
    )

    result = asyncio.run(registry.execute("loose", {"count": 1}))

    assert result.is_error is False
    assert json.loads(result.content) == {"count": 1}


def test_tool_executor_runs_calls_concurrently_and_preserves_order():
    registry = ToolRegistry()
    calls = []

    async def slow(text):
        await asyncio.sleep(0.02)
        calls.append(text)
        return text

    async def fast(text):
        calls.append(text)
        return text

    registry.register("slow", "Slow", {}, slow)
    registry.register("fast", "Fast", {}, fast)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="slow", arguments={"text": "first"}),
                ToolCall(id="call-2", name="fast", arguments={"text": "second"}),
            ]
        )
    )

    assert [item.tool_call_id for item in results] == ["call-1", "call-2"]
    assert [item.content for item in results] == ["first", "second"]
    assert calls == ["second", "first"]


def test_tool_executor_runs_state_writes_sequentially():
    registry = ToolRegistry()
    calls = []

    async def slow_write(text):
        await asyncio.sleep(0.02)
        calls.append(text)
        return text

    async def fast_read(text):
        calls.append(text)
        return text

    registry.register("write", "Write state", {}, slow_write, metadata={"writes_state": True})
    registry.register("read", "Read state", {}, fast_read)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="write", arguments={"text": "first"}),
                ToolCall(id="call-2", name="read", arguments={"text": "second"}),
            ]
        )
    )

    assert [item.content for item in results] == ["first", "second"]
    assert calls == ["first", "second"]


def test_tool_executor_runs_non_concurrency_safe_tools_sequentially():
    registry = ToolRegistry()
    calls = []

    async def slow_exclusive(text):
        await asyncio.sleep(0.02)
        calls.append(text)
        return text

    async def fast_read(text):
        calls.append(text)
        return text

    registry.register(
        "exclusive",
        "Exclusive",
        {},
        slow_exclusive,
        metadata={"concurrency_safe": False},
    )
    registry.register("read", "Read", {}, fast_read)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="exclusive", arguments={"text": "first"}),
                ToolCall(id="call-2", name="read", arguments={"text": "second"}),
            ]
        )
    )

    assert [item.content for item in results] == ["first", "second"]
    assert calls == ["first", "second"]


def test_tool_executor_cancel_on_error_contract_cancels_sibling_tools():
    registry = ToolRegistry()
    cancelled = {"slow": False}

    async def fail_fast():
        raise RuntimeError("broken")

    async def slow_tool():
        try:
            await asyncio.sleep(1)
            return "too late"
        except asyncio.CancelledError:
            cancelled["slow"] = True
            raise

    registry.register("fail", "Fail", {}, fail_fast, metadata={"cancels_siblings_on_error": True})
    registry.register("slow", "Slow", {}, slow_tool)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="fail"),
                ToolCall(id="call-2", name="slow"),
            ]
        )
    )

    assert [item.tool_call_id for item in results] == ["call-1", "call-2"]
    assert results[0].is_error is True
    assert "broken" in results[0].content
    assert results[1].is_error is True
    assert results[1].raw["error"] == "tool_execution_canceled"
    assert results[1].raw["canceled_by"] == "fail"
    assert cancelled["slow"] is True


def test_tool_executor_default_error_does_not_cancel_sibling_tools():
    registry = ToolRegistry()
    calls = []

    async def fail_fast():
        raise RuntimeError("broken")

    async def slow_tool():
        await asyncio.sleep(0.02)
        calls.append("slow")
        return "done"

    registry.register("fail", "Fail", {}, fail_fast)
    registry.register("slow", "Slow", {}, slow_tool)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="fail"),
                ToolCall(id="call-2", name="slow"),
            ]
        )
    )

    assert results[0].is_error is True
    assert results[1].content == "done"
    assert calls == ["slow"]


def test_tool_executor_external_cancel_returns_synthetic_results_for_pending_tools():
    registry = ToolRegistry()
    started = None
    cancelled = {"slow": False}

    async def slow_tool():
        assert started is not None
        started.set()
        try:
            await asyncio.sleep(1)
            return "too late"
        except asyncio.CancelledError:
            cancelled["slow"] = True
            raise

    registry.register("slow", "Slow", {}, slow_tool)

    async def run_and_cancel():
        nonlocal started
        started = asyncio.Event()
        task = asyncio.create_task(registry.execute_many([ToolCall(id="call-1", name="slow")]))
        await started.wait()
        task.cancel()
        return await task

    results = asyncio.run(run_and_cancel())

    assert [item.tool_call_id for item in results] == ["call-1"]
    assert results[0].is_error is True
    assert results[0].raw["error"] == "tool_execution_canceled"
    assert results[0].raw["cancel_reason"] == "user_interrupted"
    assert cancelled["slow"] is True


def test_tool_executor_external_cancel_returns_results_for_remaining_sequential_tools():
    registry = ToolRegistry()
    started = None
    calls = []

    async def slow_exclusive():
        assert started is not None
        started.set()
        try:
            await asyncio.sleep(1)
            return "too late"
        except asyncio.CancelledError:
            calls.append("cancelled")
            raise

    async def later_tool():
        calls.append("later")
        return "later"

    registry.register("exclusive", "Exclusive", {}, slow_exclusive, metadata={"concurrency_safe": False})
    registry.register("later", "Later", {}, later_tool)

    async def run_and_cancel():
        nonlocal started
        started = asyncio.Event()
        task = asyncio.create_task(
            registry.execute_many(
                [
                    ToolCall(id="call-1", name="exclusive"),
                    ToolCall(id="call-2", name="later"),
                ]
            )
        )
        await started.wait()
        task.cancel()
        return await task

    results = asyncio.run(run_and_cancel())

    assert [item.tool_call_id for item in results] == ["call-1", "call-2"]
    assert [item.raw["cancel_reason"] for item in results] == ["user_interrupted", "user_interrupted"]
    assert calls == ["cancelled"]


def test_tool_executor_interrupt_cancel_waits_for_blocking_tools():
    registry = ToolRegistry()
    started = None

    async def slow_blocking():
        assert started is not None
        started.set()
        await asyncio.sleep(0.02)
        return "finished"

    registry.register("slow", "Slow", {}, slow_blocking)

    async def run_and_interrupt():
        nonlocal started
        started = asyncio.Event()
        task = asyncio.create_task(registry.execute_many([ToolCall(id="call-1", name="slow")]))
        await started.wait()
        task.cancel("interrupt")
        return await task

    results = asyncio.run(run_and_interrupt())

    assert [item.tool_call_id for item in results] == ["call-1"]
    assert results[0].is_error is False
    assert results[0].content == "finished"


def test_tool_executor_interrupt_cancel_cancels_explicit_cancel_tools():
    registry = ToolRegistry()
    started = None

    async def slow_cancelable():
        assert started is not None
        started.set()
        await asyncio.sleep(1)
        return "too late"

    registry.register("slow", "Slow", {}, slow_cancelable, metadata={"interrupt_behavior": "cancel"})

    async def run_and_interrupt():
        nonlocal started
        started = asyncio.Event()
        task = asyncio.create_task(registry.execute_many([ToolCall(id="call-1", name="slow")]))
        await started.wait()
        task.cancel("interrupt")
        return await task

    results = asyncio.run(run_and_interrupt())

    assert results[0].is_error is True
    assert results[0].raw["cancel_reason"] == "user_interrupted"


def test_tool_executor_truncates_result_when_limit_is_configured():
    registry = ToolRegistry()
    registry.register("long", "Long", {}, lambda: "abcdef", metadata={"max_result_size_chars": 3})

    result = asyncio.run(registry.execute("long", {}))

    assert result.content == "abc\n[tool result truncated]"
    assert result.raw["_meta"]["result_truncated"] is True


def test_filesystem_read_formats_line_ranges_and_does_not_record_partial_read(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    partial = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "offset": 2, "limit": 2}))
    write = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert partial.is_error is False
    assert partial.content.startswith("2\ttwo\n3\tthree")
    assert "[Read partial file view: startLine=2, numLines=2, totalLines=4]" in partial.content
    assert partial.raw["type"] == "text"
    assert partial.raw["content"] == "two\nthree\n"
    assert partial.raw["startLine"] == 2
    assert partial.raw["numLines"] == 2
    assert partial.raw["totalLines"] == 4
    assert partial.raw["isPartialView"] is True
    assert partial.raw["file"] == {
        "filePath": "notes.txt",
        "content": "two\nthree\n",
        "numLines": 2,
        "startLine": 2,
        "totalLines": 4,
    }
    assert write.is_error is True
    assert "File has not been read yet" in write.content


def test_filesystem_read_rejects_oversized_full_text_but_allows_limited_range(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    (tmp_path / "medium.txt").write_text("x\n" * 11000, encoding="utf-8")
    (tmp_path / "medium-alias.txt").write_text("y\n" * 11000, encoding="utf-8")
    full = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "max_bytes": 8}))
    limited = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt", "max_bytes": 8, "limit": 1}))
    default_full = asyncio.run(registry.execute("filesystem.read", {"path": "medium.txt"}))
    alias_default_full = asyncio.run(registry.execute("Read", {"file_path": "medium-alias.txt"}))

    assert full.is_error is True
    assert "File content" in full.content
    assert "Use offset and limit parameters" in full.content
    assert limited.is_error is False
    assert limited.raw["type"] == "text"
    assert limited.raw["content"] == "one\n"
    assert limited.raw["isPartialView"] is True
    assert limited.content.startswith("1\tone")
    assert default_full.is_error is False
    assert default_full.raw["bytes"] > 20000
    assert alias_default_full.is_error is False
    assert alias_default_full.raw["bytes"] > 20000


def test_filesystem_read_missing_file_reports_cwd_and_similar_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "README.md").write_text("notes\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "README.txt"}))

    assert result.is_error is True
    assert "File does not exist" in result.content
    assert "Note: your current working directory is %s" % tmp_path in result.content
    assert "Did you mean README.md?" in result.content


def test_filesystem_read_missing_nested_file_suggests_filename_only(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("notes\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "docs/guide.txt"}))

    assert result.is_error is True
    assert "Did you mean guide.md?" in result.content
    assert "Did you mean docs/guide.md?" not in result.content


def test_filesystem_read_directory_reports_src_origin_eisdir(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "docs").mkdir()
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "docs"}))

    assert result.is_error is True
    assert "EISDIR: illegal operation on a directory, read 'docs'" in result.content


def test_filesystem_read_blocks_device_paths_before_sandbox_resolution(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "/dev/random"}))
    proc_result = asyncio.run(registry.execute("filesystem.read", {"path": "/proc/self/fd/0"}))

    assert result.is_error is True
    assert result.content == "Cannot read '/dev/random': this device file would block or produce infinite output."
    assert proc_result.is_error is True
    assert proc_result.content == "Cannot read '/proc/self/fd/0': this device file would block or produce infinite output."


def test_filesystem_read_binary_reports_src_origin_binary_error(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "payload.zip").write_bytes(b"not a real zip")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "payload.zip"}))

    assert result.is_error is True
    assert (
        result.content
        == "This tool cannot read binary files. The file appears to be a binary .zip file. "
        "Please use appropriate tools for binary file analysis."
    )


def test_filesystem_read_binary_extension_rejects_before_missing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "missing.zip"}))
    image_result = asyncio.run(registry.execute("filesystem.read", {"path": "missing.png"}))

    assert result.is_error is True
    assert (
        result.content
        == "This tool cannot read binary files. The file appears to be a binary .zip file. "
        "Please use appropriate tools for binary file analysis."
    )
    assert "File does not exist" not in result.content
    assert image_result.is_error is True
    assert "File does not exist" in image_result.content


def test_filesystem_read_prefixes_stale_memory_freshness_note(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    memory_path = tmp_path / ".agents" / "memory" / "project.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("old repo fact\n", encoding="utf-8")
    stale_mtime = time.time() - (4 * 86400)
    os.utime(memory_path, (stale_mtime, stale_mtime))
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": ".agents/memory/project.md"}))

    assert result.is_error is False
    assert result.raw["memoryFreshness"]["ageDays"] >= 3
    assert result.raw["memoryFreshness"]["memoryKind"] == "auto"
    assert result.raw["memoryFreshness"]["scope"] == "personal"
    assert result.content.startswith("<system-reminder>This memory is ")
    assert "Memories are point-in-time observations, not live state" in result.content
    assert "1\told repo fact" in result.content


def test_filesystem_read_detects_managed_memory_freshness_paths(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    stale_mtime = time.time() - (5 * 86400)
    cases = [
        (".agents/memory/team/MEMORY.md", "team", "team"),
        (".agents/projects/project-key/memory/MEMORY.md", "auto", "personal"),
        (".agents/projects/project-key/memory/team/MEMORY.md", "team", "team"),
        (".claude/agent-memory/reviewer/MEMORY.md", "agent", "project"),
        (".claude/agent-memory-local/reviewer/MEMORY.md", "agent", "local"),
        (".claude/session-memory/summary.md", "session", "session"),
    ]
    for relative_path, _, _ in cases:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("remember %s\n" % relative_path, encoding="utf-8")
        os.utime(path, (stale_mtime, stale_mtime))
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    for relative_path, memory_kind, scope in cases:
        result = asyncio.run(registry.execute("filesystem.read", {"path": relative_path}))

        assert result.is_error is False
        assert result.raw["memoryFreshness"]["ageDays"] >= 4
        assert result.raw["memoryFreshness"]["memoryKind"] == memory_kind
        assert result.raw["memoryFreshness"]["scope"] == scope
        assert result.content.startswith("<system-reminder>This memory is ")
        assert "1\tremember %s" % relative_path in result.content


def test_filesystem_read_does_not_prefix_fresh_memory_or_regular_markdown(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    memory_path = tmp_path / ".agents" / "memory" / "fresh.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("fresh memory\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("regular project doc\n", encoding="utf-8")
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    rule_md = tmp_path / ".claude" / "rules" / "style.md"
    unmanaged_claude_memory = tmp_path / ".claude" / "memory" / "note.md"
    claude_md.parent.mkdir(parents=True)
    rule_md.parent.mkdir(parents=True)
    unmanaged_claude_memory.parent.mkdir(parents=True)
    claude_md.write_text("project instructions\n", encoding="utf-8")
    rule_md.write_text("project rule\n", encoding="utf-8")
    unmanaged_claude_memory.write_text("unmanaged memory-shaped doc\n", encoding="utf-8")
    stale_mtime = time.time() - (5 * 86400)
    os.utime(claude_md, (stale_mtime, stale_mtime))
    os.utime(rule_md, (stale_mtime, stale_mtime))
    os.utime(unmanaged_claude_memory, (stale_mtime, stale_mtime))
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    fresh = asyncio.run(registry.execute("filesystem.read", {"path": ".agents/memory/fresh.md"}))
    regular = asyncio.run(registry.execute("filesystem.read", {"path": "MEMORY.md"}))
    claude = asyncio.run(registry.execute("filesystem.read", {"path": ".claude/CLAUDE.md"}))
    rule = asyncio.run(registry.execute("filesystem.read", {"path": ".claude/rules/style.md"}))
    unmanaged = asyncio.run(registry.execute("filesystem.read", {"path": ".claude/memory/note.md"}))

    assert fresh.is_error is False
    assert "memoryFreshness" not in fresh.raw
    assert fresh.content.startswith("1\tfresh memory")
    assert regular.is_error is False
    assert "memoryFreshness" not in regular.raw
    assert regular.content.startswith("1\tregular project doc")
    assert claude.is_error is False
    assert "memoryFreshness" not in claude.raw
    assert claude.content.startswith("1\tproject instructions")
    assert rule.is_error is False
    assert "memoryFreshness" not in rule.raw
    assert rule.content.startswith("1\tproject rule")
    assert unmanaged.is_error is False
    assert "memoryFreshness" not in unmanaged.raw
    assert unmanaged.content.startswith("1\tunmanaged memory-shaped doc")


def test_filesystem_write_rejects_secret_content_in_team_memory(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    (tmp_path / ".agents" / "memory" / "team").mkdir(parents=True)
    (tmp_path / ".agents" / "memory").mkdir(parents=True, exist_ok=True)
    fake_github_token = "ghp_" + "A" * 36

    blocked = asyncio.run(
        registry.execute(
            "filesystem.write",
            {"path": ".agents/memory/team/MEMORY.md", "content": "token=%s\n" % fake_github_token},
        )
    )
    personal = asyncio.run(
        registry.execute(
            "filesystem.write",
            {"path": ".agents/memory/MEMORY.md", "content": "token=%s\n" % fake_github_token},
        )
    )

    assert blocked.is_error is True
    assert "Content contains potential secrets (GitHub PAT)" in blocked.content
    assert "Team memory is shared with all repository collaborators" in blocked.content
    assert not (tmp_path / ".agents" / "memory" / "team" / "MEMORY.md").exists()
    assert personal.is_error is False
    assert (tmp_path / ".agents" / "memory" / "MEMORY.md").read_text(encoding="utf-8").startswith("token=ghp_")


def test_filesystem_read_returns_src_origin_style_image_payload(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (tmp_path / "pixel.png").write_bytes(png_bytes)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "pixel.png"}))

    assert result.is_error is False
    assert result.raw["type"] == "image"
    assert result.raw["path"] == "pixel.png"
    assert result.raw["mimeType"] == "image/png"
    assert result.raw["bytes"] == len(png_bytes)
    assert result.raw["file"]["filePath"] == "pixel.png"
    assert result.raw["file"]["type"] == "image/png"
    assert result.raw["file"]["originalSize"] == len(png_bytes)
    assert result.raw["file"]["dimensions"] == {
        "originalWidth": 1,
        "originalHeight": 1,
        "displayWidth": 1,
        "displayHeight": 1,
    }
    assert base64.b64decode(result.raw["file"]["base64"]) == png_bytes
    assert result.content == "Image file read: pixel.png (image/png, %d bytes)" % len(png_bytes)


def test_filesystem_read_retries_macos_screenshot_thin_space_variant(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    thin_space = "\u202f"
    actual_path = "Screenshot 2026-05-21 at 10.15.00%sAM.png" % thin_space
    (tmp_path / actual_path).write_bytes(png_bytes)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "Screenshot 2026-05-21 at 10.15.00 AM.png"}))

    assert result.is_error is False
    assert result.raw["type"] == "image"
    assert result.raw["path"] == actual_path
    assert result.raw["file"]["filePath"] == actual_path
    assert base64.b64decode(result.raw["file"]["base64"]) == png_bytes


def test_filesystem_read_image_empty_and_unknown_format_follow_src_origin(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "empty.png").write_bytes(b"")
    (tmp_path / "unknown.jpg").write_bytes(b"not really an image")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    empty = asyncio.run(registry.execute("filesystem.read", {"path": "empty.png"}))
    unknown = asyncio.run(registry.execute("filesystem.read", {"path": "unknown.jpg"}))

    assert empty.is_error is True
    assert empty.content == "Image file is empty: empty.png"
    assert unknown.is_error is False
    assert unknown.raw["mimeType"] == "image/png"
    assert unknown.raw["file"]["type"] == "image/png"
    assert "dimensions" not in unknown.raw["file"]
    assert base64.b64decode(unknown.raw["file"]["base64"]) == b"not really an image"


def test_filesystem_read_returns_src_origin_style_pdf_payload(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    (tmp_path / "sample.pdf").write_bytes(pdf_bytes)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "sample.pdf"}))
    pages = asyncio.run(registry.execute("filesystem.read", {"path": "sample.pdf", "pages": "1-25"}))

    assert result.is_error is False
    assert result.raw["type"] == "pdf"
    assert result.raw["path"] == "sample.pdf"
    assert result.raw["mimeType"] == "application/pdf"
    assert result.raw["bytes"] == len(pdf_bytes)
    assert result.raw["file"]["filePath"] == "sample.pdf"
    assert result.raw["file"]["originalSize"] == len(pdf_bytes)
    assert base64.b64decode(result.raw["file"]["base64"]) == pdf_bytes
    document_blocks = result.raw["newMessages"][0]["content"]
    assert document_blocks == [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": result.raw["file"]["base64"],
            },
        }
    ]
    assert result.content == "PDF file read: sample.pdf (%d bytes)" % len(pdf_bytes)
    assert pages.is_error is True
    assert "exceeds maximum of 20 pages" in pages.content


def test_filesystem_read_reports_pdf_page_extraction_dependency(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(filesystem_media.shutil, "which", lambda name: None)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "sample.pdf", "pages": "1"}))

    assert result.is_error is True
    assert "PDF page extraction requires poppler-utils" in result.content


def test_filesystem_read_extracts_pdf_pages_with_poppler(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    pdf_bytes = b"%PDF-1.4\n%%EOF\n"
    (tmp_path / "sample.pdf").write_bytes(pdf_bytes)

    def fake_run(command, text=True, capture_output=True, check=False):
        prefix = Path(command[-1])
        (prefix.parent / "page-2.jpg").write_bytes(b"\xff\xd8\xffpage2")
        (prefix.parent / "page-3.jpg").write_bytes(b"\xff\xd8\xffpage3")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(filesystem_media.shutil, "which", lambda name: "/usr/bin/pdftoppm" if name == "pdftoppm" else None)
    monkeypatch.setattr(filesystem_media.subprocess, "run", fake_run)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "sample.pdf", "pages": "2-3"}))

    assert result.is_error is False
    assert result.raw["type"] == "parts"
    assert result.raw["path"] == "sample.pdf"
    assert result.raw["pages"] == "2-3"
    assert result.raw["file"]["filePath"] == "sample.pdf"
    assert result.raw["file"]["originalSize"] == len(pdf_bytes)
    assert result.raw["file"]["count"] == 2
    assert sorted(path.name for path in Path(result.raw["file"]["outputDir"]).glob("*.jpg")) == ["page-2.jpg", "page-3.jpg"]
    image_blocks = result.raw["newMessages"][0]["content"]
    assert [block["type"] for block in image_blocks] == ["image", "image"]
    assert [block["source"]["media_type"] for block in image_blocks] == ["image/jpeg", "image/jpeg"]
    assert base64.b64decode(image_blocks[0]["source"]["data"]) == b"\xff\xd8\xffpage2"
    assert base64.b64decode(image_blocks[1]["source"]["data"]) == b"\xff\xd8\xffpage3"
    assert result.content == "PDF pages extracted: 2 page(s) from sample.pdf (%d bytes)" % len(pdf_bytes)


def test_runtime_injects_pdf_page_image_messages_after_read_tool(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    def fake_run(command, text=True, capture_output=True, check=False):
        prefix = Path(command[-1])
        (prefix.parent / "page-1.jpg").write_bytes(b"\xff\xd8\xffpage1")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(filesystem_media.shutil, "which", lambda name: "/usr/bin/pdftoppm" if name == "pdftoppm" else None)
    monkeypatch.setattr(filesystem_media.subprocess, "run", fake_run)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    model = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="toolu-read-pdf",
                            name="filesystem.read",
                            arguments={"path": "sample.pdf", "pages": "1"},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "done")),
        ]
    )
    runtime = AgentRuntime(
        model_client=model,
        tools=registry,
        protocol="scripted",
        model="scripted",
        enabled_tools=["filesystem.read"],
    )

    result = asyncio.run(runtime.run([Message.from_text("user", "read page")]))

    assert result.content == "done"
    assert [message.role for message in result.messages] == ["user", "assistant", "tool", "user", "assistant"]
    supplemental = result.messages[3]
    assert supplemental.raw["isMeta"] is True
    assert supplemental.raw["source_tool_call_id"] == "toolu-read-pdf"
    assert supplemental.content[0].type == "image"
    assert supplemental.content[0].data["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(supplemental.content[0].data["source"]["data"]) == b"\xff\xd8\xffpage1"
    assert model.requests[1].messages[3].content[0].type == "image"


def test_runtime_injects_pdf_document_messages_after_read_tool(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    (tmp_path / "sample.pdf").write_bytes(pdf_bytes)
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    model = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="toolu-read-full-pdf",
                            name="filesystem.read",
                            arguments={"path": "sample.pdf"},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "done")),
        ]
    )
    runtime = AgentRuntime(
        model_client=model,
        tools=registry,
        protocol="scripted",
        model="scripted",
        enabled_tools=["filesystem.read"],
    )

    result = asyncio.run(runtime.run([Message.from_text("user", "read pdf")]))

    assert result.content == "done"
    assert [message.role for message in result.messages] == ["user", "assistant", "tool", "user", "assistant"]
    supplemental = result.messages[3]
    assert supplemental.raw["isMeta"] is True
    assert supplemental.raw["source_tool_call_id"] == "toolu-read-full-pdf"
    assert supplemental.content[0].type == "document"
    assert supplemental.content[0].data["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(supplemental.content[0].data["source"]["data"]) == pdf_bytes
    assert model.requests[1].messages[3].content[0].type == "document"


def test_filesystem_read_returns_src_origin_style_notebook_payload(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n"], "metadata": {}},
            {"cell_type": "code", "source": ["print(1)\n"], "outputs": [], "metadata": {}},
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "analysis.ipynb", "content": json.dumps({**notebook, "metadata": {"ok": True}})}))

    assert result.is_error is False
    assert result.raw["type"] == "notebook"
    assert result.raw["path"] == "analysis.ipynb"
    assert result.raw["file"]["filePath"] == "analysis.ipynb"
    assert result.raw["file"]["cells"] == notebook["cells"]
    assert "Notebook file read: analysis.ipynb (2 cells)" in result.content
    assert '"cell_type": "markdown"' in result.content
    assert written.is_error is False


def test_notebook_edit_updates_cells_with_read_before_write_safety(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    notebook = {
        "cells": [
            {"cell_type": "markdown", "id": "intro", "source": "# Title\n", "metadata": {}},
            {
                "cell_type": "code",
                "id": "calc",
                "source": "print(1)\n",
                "outputs": [{"output_type": "stream", "text": "1\n"}],
                "execution_count": 7,
                "metadata": {},
            },
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    unread = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "calc", "new_source": "print(2)\n"},
        )
    )
    read = asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    replaced = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "calc", "new_source": "print(2)\n"},
        )
    )
    reread = asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    inserted = asyncio.run(
        registry.execute(
            "notebook.edit",
            {
                "notebook_path": "analysis.ipynb",
                "cell_id": "intro",
                "new_source": "Inserted note\n",
                "cell_type": "markdown",
                "edit_mode": "insert",
            },
        )
    )
    inserted_id = inserted.raw["cell_id"]
    deleted = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": inserted_id, "new_source": "", "edit_mode": "delete"},
        )
    )
    append_insert = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "cell-2", "new_source": "print(3)\n"},
        )
    )
    payload = json.loads((tmp_path / "analysis.ipynb").read_text(encoding="utf-8"))

    assert unread.is_error is True
    assert "Read it first before writing to it" in unread.content
    assert read.raw["type"] == "notebook"
    assert replaced.is_error is False
    assert replaced.content == "Updated cell calc with print(2)\n"
    assert replaced.raw["language"] == "python"
    assert replaced.raw["edit_mode"] == "replace"
    assert replaced.raw["notebook_path"] == "analysis.ipynb"
    assert replaced.raw["filePath"] == "analysis.ipynb"
    assert replaced.raw["cellId"] == "calc"
    assert replaced.raw["cellIndex"] == 1
    assert replaced.raw["oldString"] == "print(1)\n"
    assert replaced.raw["newString"] == "print(2)\n"
    assert replaced.raw["structuredPatch"][0]["lines"] == [
        "-print(1)",
        "+print(2)",
    ]
    assert replaced.raw["structuredPatches"][0] == {
        "filePath": "analysis.ipynb",
        "cellId": "calc",
        "cellIndex": 1,
        "editMode": "replace",
        "hunks": replaced.raw["structuredPatch"],
    }
    assert replaced.raw["editSummary"][0] == {
        "filePath": "analysis.ipynb",
        "cellId": "calc",
        "cellIndex": 1,
        "cellType": "code",
        "editMode": "replace",
        "oldString": "print(1)\n",
        "newString": "print(2)\n",
        "replaceAll": False,
        "occurrences": 1,
    }
    assert replaced.raw["original_file"] == json.dumps(notebook)
    assert replaced.raw["originalFile"] == replaced.raw["original_file"]
    assert '"print(2)\\n"' in replaced.raw["updated_file"]
    assert replaced.raw["updatedFile"] == replaced.raw["updated_file"]
    assert reread.raw["type"] == "notebook"
    assert reread.raw["file"]["cells"][1]["source"] == "print(2)\n"
    assert inserted.is_error is False
    assert inserted.content == "Inserted cell %s with Inserted note\n" % inserted_id
    assert inserted.raw["cell_type"] == "markdown"
    assert inserted.raw["oldString"] == ""
    assert inserted.raw["structuredPatch"][0]["lines"] == ["+Inserted note"]
    assert deleted.is_error is False
    assert deleted.content == "Deleted cell %s" % inserted_id
    assert deleted.raw["newString"] == ""
    assert deleted.raw["structuredPatch"][0]["lines"] == ["-Inserted note"]
    assert append_insert.is_error is False
    assert append_insert.raw["edit_mode"] == "insert"
    assert append_insert.raw["cell_type"] == "code"
    assert append_insert.raw["oldString"] == ""
    assert append_insert.raw["newString"] == "print(3)\n"
    assert append_insert.content == "Inserted cell %s with print(3)\n" % append_insert.raw["cell_id"]
    assert len(payload["cells"]) == 3
    assert payload["cells"][1]["source"] == "print(2)\n"
    assert payload["cells"][1]["execution_count"] is None
    assert payload["cells"][1]["outputs"] == []
    assert payload["cells"][2]["cell_type"] == "code"
    assert payload["cells"][2]["source"] == "print(3)\n"
    assert payload["cells"][2]["execution_count"] is None
    assert payload["cells"][2]["outputs"] == []

    impact = describe_tool_impact(
        ToolCall(
            id="call-notebook",
            name="notebook.edit",
            arguments={"notebook_path": "analysis.ipynb", "cell_id": "calc", "new_source": "print(3)\n"},
        )
    )
    assert impact.risk == "medium"
    assert impact.operations == ["file_write", "notebook_edit"]
    assert impact.paths == ["analysis.ipynb"]
    assert impact.writes_files is True
    assert "print(3)" in impact.diff_preview


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink is not available on this platform")
def test_notebook_edit_reports_symlink_target_for_followed_writes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    notebook = {
        "cells": [{"cell_type": "code", "id": "calc", "source": "print(1)\n", "metadata": {}}],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    target = tmp_path / "target.ipynb"
    link = tmp_path / "link.ipynb"
    target.write_text(json.dumps(notebook), encoding="utf-8")
    link.symlink_to(target.name)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "link.ipynb"}))
    edited = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "link.ipynb", "cell_id": "calc", "new_source": "print(2)\n"},
        )
    )
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert read.is_error is False
    assert edited.is_error is False
    assert edited.raw["filePath"] == "target.ipynb"
    assert edited.raw["symlinkTarget"] == "target.ipynb"
    assert link.is_symlink()
    assert payload["cells"][0]["source"] == "print(2)\n"


def test_notebook_edit_rejects_stale_and_invalid_notebook_edits(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    notebook = {
        "cells": [{"cell_type": "markdown", "id": "intro", "source": "# Title\n", "metadata": {}}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    (tmp_path / "analysis.ipynb").write_text(json.dumps({**notebook, "metadata": {"changed": True}}), encoding="utf-8")

    stale = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "intro", "new_source": "changed"},
        )
    )
    asyncio.run(registry.execute("filesystem.read", {"path": "analysis.ipynb"}))
    missing_cell_type = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "new_source": "inserted", "edit_mode": "insert"},
        )
    )
    missing_cell = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "analysis.ipynb", "cell_id": "missing", "new_source": "changed"},
        )
    )
    wrong_file = asyncio.run(
        registry.execute(
            "notebook.edit",
            {"notebook_path": "notes.py", "cell_id": "intro", "new_source": "changed"},
        )
    )

    assert stale.is_error is True
    assert "modified since read" in stale.content
    assert missing_cell_type.is_error is True
    assert "Cell type is required" in missing_cell_type.content
    assert missing_cell.is_error is True
    assert 'Cell with ID "missing" not found' in missing_cell.content
    assert wrong_file.is_error is True
    assert "Jupyter notebook" in wrong_file.content


def test_filesystem_read_deduplicates_unchanged_full_reads_without_breaking_write_safety(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    first = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    second = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert first.is_error is False
    assert first.content == "1\told"
    assert first.raw["type"] == "text"
    assert first.raw["file"]["filePath"] == "notes.txt"
    assert first.raw["file"]["content"] == "old\n"
    assert first.raw["file"]["numLines"] == 1
    assert first.raw["file"]["startLine"] == 1
    assert first.raw["file"]["totalLines"] == 1
    assert second.is_error is False
    assert second.raw["type"] == "file_unchanged"
    assert second.raw["file"] == {"filePath": "notes.txt"}
    assert second.raw["deduplicated"] is True
    assert "File unchanged since last read" in second.content
    assert written.is_error is False
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "new\n"


def test_filesystem_read_dedup_is_invalidated_when_file_changes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    first = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    (tmp_path / "notes.txt").write_text("changed\n", encoding="utf-8")
    second = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))

    assert first.is_error is False
    assert second.is_error is False
    assert second.raw["content"] == "changed\n"
    assert second.content == "1\tchanged"


def test_filesystem_write_requires_read_before_overwriting_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    blocked = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))
    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert blocked.is_error is True
    assert "File has not been read yet" in blocked.content
    assert read.is_error is False
    assert written.is_error is False
    assert written.raw["type"] == "update"
    assert written.raw["filePath"] == "notes.txt"
    assert written.raw["content"] == "new\n"
    assert written.raw["originalFile"] == "old\n"
    assert written.raw["structuredPatch"][0]["lines"] == ["-old", "+new"]
    assert written.raw["safety"]["required_prior_read"] is True
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "new\n"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink is not available on this platform")
def test_filesystem_write_reports_symlink_target_for_followed_writes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    target = tmp_path / "target.txt"
    link = tmp_path / "link.txt"
    target.write_text("old\n", encoding="utf-8")
    link.symlink_to(target.name)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "link.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "link.txt", "content": "new\n"}))

    assert read.is_error is False
    assert written.is_error is False
    assert written.raw["filePath"] == "target.txt"
    assert written.raw["symlinkTarget"] == "target.txt"
    assert written.raw["safety"]["symlink_target"] == "target.txt"
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == "new\n"


def test_filesystem_write_exposes_src_origin_git_diff_for_tracked_file(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    _run_git(repo, "remote", "add", "origin", "git@github.com:example/agents-test.git")
    (repo / "tracked.py").write_text("value = 'old'\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.py")
    _run_git(repo, "commit", "-m", "initial")
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "tracked.py"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "tracked.py", "content": "value = 'new'\n"}))

    assert read.is_error is False
    assert written.is_error is False
    assert written.raw["gitDiff"]["filename"] == "tracked.py"
    assert written.raw["gitDiff"]["status"] == "modified"
    assert written.raw["gitDiff"]["additions"] == 1
    assert written.raw["gitDiff"]["deletions"] == 1
    assert written.raw["gitDiff"]["changes"] == 2
    assert written.raw["gitDiff"]["repository"] == "example/agents-test"
    assert "-value = 'old'" in written.raw["gitDiff"]["patch"]
    assert "+value = 'new'" in written.raw["gitDiff"]["patch"]


def test_filesystem_write_git_diff_uses_base_ref_merge_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    (repo / "tracked.py").write_text("value = 'old'\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.py")
    _run_git(repo, "commit", "-m", "initial")
    _run_git(repo, "checkout", "-b", "feature")
    (repo / "tracked.py").write_text("value = 'middle'\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.py")
    _run_git(repo, "commit", "-m", "feature change")
    monkeypatch.setenv("CLAUDE_CODE_BASE_REF", "main")
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "tracked.py"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "tracked.py", "content": "value = 'new'\n"}))

    assert read.is_error is False
    assert written.is_error is False
    assert written.raw["gitDiff"]["filename"] == "tracked.py"
    assert "-value = 'old'" in written.raw["gitDiff"]["patch"]
    assert "-value = 'middle'" not in written.raw["gitDiff"]["patch"]
    assert "+value = 'new'" in written.raw["gitDiff"]["patch"]


def test_filesystem_write_exposes_src_origin_git_diff_for_created_file(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    _run_git(repo, "remote", "add", "origin", "https://github.com/example/agents-test.git")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    written = asyncio.run(registry.execute("Write", {"file_path": "created_module.py", "content": "print('new')\n"}))

    assert written.is_error is False
    assert written.raw["gitDiff"]["filename"] == "created_module.py"
    assert written.raw["gitDiff"]["status"] == "added"
    assert written.raw["gitDiff"]["additions"] == 1
    assert written.raw["gitDiff"]["deletions"] == 0
    assert written.raw["gitDiff"]["changes"] == 1
    assert written.raw["gitDiff"]["repository"] == "example/agents-test"
    assert "+print('new')" in written.raw["gitDiff"]["patch"]


def test_filesystem_write_strips_trailing_whitespace_for_non_markdown(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    written = asyncio.run(
        registry.execute("filesystem.write", {"path": "notes.txt", "content": "alpha   \nnext\t  "})
    )

    assert written.is_error is False
    assert written.raw["type"] == "create"
    assert written.raw["filePath"] == "notes.txt"
    assert written.raw["content"] == "alpha\nnext"
    assert written.raw["originalFile"] is None
    assert written.raw["structuredPatch"] == []
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "alpha\nnext"


def test_filesystem_write_preserves_markdown_trailing_whitespace(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    written = asyncio.run(
        registry.execute("filesystem.write", {"path": "guide.md", "content": "alpha  \nnext\t  "})
    )

    assert written.is_error is False
    assert written.raw["content"] == "alpha  \nnext\t  "
    assert (tmp_path / "guide.md").read_text(encoding="utf-8") == "alpha  \nnext\t  "


def test_filesystem_write_rejects_stale_prior_read(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    (tmp_path / "notes.txt").write_text("changed outside\n", encoding="utf-8")
    stale = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert read.is_error is False
    assert stale.is_error is True
    assert "modified since read" in stale.content
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "changed outside\n"


def test_filesystem_write_uses_provided_line_endings_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_bytes(b"old\r\ntext\r\n")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\ntext\n"}))

    assert read.is_error is False
    assert written.is_error is False
    assert written.raw["safety"]["line_endings"] == "lf"
    assert (tmp_path / "notes.txt").read_bytes() == b"new\ntext\n"


def test_filesystem_write_preserves_utf16le_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-16")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))

    assert read.is_error is False
    assert read.raw["encoding"] == "utf-16le"
    assert written.is_error is False
    assert written.raw["encoding"] == "utf-16le"
    assert written.raw["safety"]["encoding"] == "utf-16le"
    assert (tmp_path / "notes.txt").read_bytes().startswith(b"\xff\xfe")
    assert (tmp_path / "notes.txt").read_text(encoding="utf-16") == "new\n"


def test_filesystem_write_preserves_utf16_without_bom_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_bytes("old\n".encode("utf-16le"))
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))
    payload = (tmp_path / "notes.txt").read_bytes()

    assert read.is_error is False
    assert read.raw["encoding"] == "utf-16le"
    assert written.is_error is False
    assert written.raw["encoding"] == "utf-16le"
    assert not payload.startswith(b"\xff\xfe")
    assert payload.decode("utf-16le") == "new\n"


def test_filesystem_write_preserves_utf16be_bom_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_bytes(b"\xfe\xff" + "old\n".encode("utf-16be"))
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    written = asyncio.run(registry.execute("filesystem.write", {"path": "notes.txt", "content": "new\n"}))
    payload = (tmp_path / "notes.txt").read_bytes()

    assert read.is_error is False
    assert read.raw["encoding"] == "utf-16be"
    assert written.is_error is False
    assert written.raw["encoding"] == "utf-16be"
    assert payload.startswith(b"\xfe\xff")
    assert payload[2:].decode("utf-16be") == "new\n"


def test_text_edit_tools_reject_binary_files(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "payload.bin").write_bytes(b"old\x00binary")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "payload.bin"}))
    write = asyncio.run(registry.execute("filesystem.write", {"path": "payload.bin", "content": "new"}))
    patch = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "payload.bin", "old_text": "old", "new_text": "new"}]},
        )
    )

    assert read.is_error is True
    assert write.is_error is True
    assert patch.is_error is True
    assert "binary" in read.content
    assert "binary" in write.content
    assert "binary" in patch.content
    assert (tmp_path / "payload.bin").read_bytes() == b"old\x00binary"


def test_tool_executor_converts_failures_to_error_results():
    registry = ToolRegistry()

    def fail():
        raise RuntimeError("broken")

    registry.register("fail", "Fail", {}, fail)

    results = asyncio.run(registry.execute_many([ToolCall(id="call-1", name="fail")]))

    assert results[0].is_error is True
    assert "broken" in results[0].content


def test_builtin_memory_tools_manage_visible_memories(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    store = InMemoryMemoryStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        memory_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    added = asyncio.run(
        registry.execute(
            "memory.add",
            {"content": "Prefer concise implementation notes", "scope": "workspace"},
        )
    )
    short_id = added.raw["memory"]["short_id"]
    listed = asyncio.run(registry.execute("memory.list", {"query": "concise"}))
    edited = asyncio.run(
        registry.execute(
            "memory.edit",
            {"memory_id": short_id, "content": "Prefer concise verification notes"},
        )
    )
    forgotten = asyncio.run(registry.execute("memory.forget", {"memory_id": short_id}))

    records = asyncio.run(store.list_for_context("tenant", "user", agent_id="agent", workspace_id="workspace"))
    assert added.raw["memory"]["scope"] == MemoryScope.WORKSPACE.value
    assert added.raw["memory"]["metadata"]["source"] == "tool"
    assert listed.raw["memories"][0]["short_id"] == short_id
    assert edited.raw["memory"]["content"] == "Prefer concise verification notes"
    assert forgotten.raw["forgotten"] is True
    assert records == []


def test_builtin_task_tools_manage_tracked_tasks(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "task.create",
            {"title": "Build task tools", "input": "Add model-callable task tools"},
        )
    )
    task_id = created.raw["task"]["task_id"]
    short_id = created.raw["task"]["short_id"]
    listed = asyncio.run(registry.execute("task.list", {}))
    loaded = asyncio.run(registry.execute("task.get", {"task_id": short_id}))
    updated = asyncio.run(registry.execute("task.update", {"task_id": short_id, "status": "running"}))

    assert created.is_error is False
    assert listed.raw["tasks"][0]["task_id"] == task_id
    assert loaded.raw["task"]["title"] == "Build task tools"
    assert updated.raw["task"]["status"] == "running"
    assert asyncio.run(store.load_task(task_id)).status == TaskStatus.RUNNING

    async def add_output():
        engine = TaskEngine(store)
        step = await engine.add_step(task_id, name="terminal", input="work")
        await engine.start_step(step.step_id)
        await engine.finish_step(step.step_id, output="step output")

    asyncio.run(add_output())
    output = asyncio.run(registry.execute("task.output", {"task_id": short_id}))
    stopped = asyncio.run(registry.execute("task.stop", {"task_id": short_id}))

    assert "step output" in output.raw["output"]
    assert stopped.raw["task"]["status"] == "canceled"
    assert asyncio.run(store.load_task(task_id)).status == TaskStatus.CANCELED


def test_src_origin_task_schedule_toolsearch_and_plan_aliases(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    task_store = InMemoryTaskStore()
    schedule_store = InMemoryScheduleStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=task_store,
        schedule_store=schedule_store,
        agent_spec=spec,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "TaskCreate",
            {
                "subject": "Build aliases",
                "description": "Add src-origin task aliases",
                "activeForm": "Building aliases",
                "metadata": {"kind": "parity"},
            },
        )
    )
    task_id = created.raw["task"]["task_id"]
    short_id = created.raw["task"]["short_id"]
    updated = asyncio.run(
        registry.execute(
            "TaskUpdate",
            {
                "taskId": short_id,
                "subject": "Build more aliases",
                "description": "Cover task update parity",
                "status": "in_progress",
                "owner": "agent",
                "metadata": {"kind": "parity-v2"},
            },
        )
    )
    listed = asyncio.run(registry.execute("TaskList", {}))
    loaded = asyncio.run(registry.execute("TaskGet", {"taskId": short_id}))
    invalid_created = asyncio.run(
        registry.execute(
            "TaskCreate",
            {"subject": "Bad alias", "description": "Reject extra fields", "unused": True},
        )
    )
    invalid_listed = asyncio.run(registry.execute("TaskList", {"unused": True}))
    invalid_loaded = asyncio.run(registry.execute("TaskGet", {"taskId": short_id, "unused": True}))
    invalid_updated = asyncio.run(registry.execute("TaskUpdate", {"taskId": short_id, "status": "running"}))
    deleted = asyncio.run(registry.execute("TaskUpdate", {"taskId": short_id, "status": "deleted"}))
    missing_update = asyncio.run(registry.execute("TaskUpdate", {"taskId": short_id, "status": "completed"}))
    searched = asyncio.run(registry.execute("ToolSearch", {"query": "TaskCreate", "max_results": 3}))
    selected = asyncio.run(registry.execute("ToolSearch", {"query": "select:TaskCreate,CronCreate", "max_results": 5}))
    invalid_searched = asyncio.run(
        registry.execute("ToolSearch", {"query": "TaskCreate", "max_results": 3, "include_all": True})
    )

    assert created.is_error is False
    assert created.content == "Task #%s created successfully: Build aliases" % short_id
    assert listed.raw["tasks"][0]["task_id"] == task_id
    assert listed.content == "#%s [in_progress] Build more aliases (agent)" % short_id
    assert loaded.content == (
        "Task #%s: Build more aliases\n"
        "Status: in_progress\n"
        "Description: Cover task update parity"
    ) % short_id
    assert updated.content == "Updated task #%s subject, description, status, owner, metadata" % short_id
    assert updated.raw["task"]["title"] == "Build more aliases"
    assert updated.raw["task"]["input"] == "Cover task update parity"
    assert updated.raw["task"]["status"] == "running"
    assert updated.raw["task"]["metadata"]["owner"] == "agent"
    assert updated.raw["statusChange"] == {"from": "pending", "to": "in_progress"}
    assert loaded.raw["task"]["metadata"]["kind"] == "parity-v2"
    assert invalid_created.raw["details"] == "unexpected argument: unused"
    assert invalid_listed.raw["details"] == "unexpected argument: unused"
    assert invalid_loaded.raw["details"] == "unexpected argument: unused"
    assert invalid_updated.raw["details"] == "status must be one of pending, in_progress, completed, deleted"
    assert deleted.content == "Updated task #%s deleted" % short_id
    assert deleted.raw["success"] is True
    assert deleted.raw["statusChange"] == {"from": "in_progress", "to": "deleted"}
    assert asyncio.run(task_store.load_task(task_id)) is None
    assert missing_update.is_error is False
    assert missing_update.content == "Task not found"
    assert "TaskCreate" in searched.raw["matches"]
    assert searched.raw["total_deferred_tools"] >= 1
    assert "TaskCreate" in searched.content.splitlines()
    assert selected.raw["matches"] == ["TaskCreate", "CronCreate"]
    assert invalid_searched.raw["details"] == "unexpected argument: include_all"

    cron = asyncio.run(
        registry.execute(
            "CronCreate",
            {"cron": "0 9 * * *", "prompt": "Check repository health", "recurring": True, "durable": False},
        )
    )
    cron_id = cron.raw["schedule"]["short_id"]
    cron_list = asyncio.run(registry.execute("CronList", {}))
    invalid_cron_create = asyncio.run(registry.execute("CronCreate", {"cron": "bad", "prompt": "reject"}))
    invalid_cron_list = asyncio.run(registry.execute("CronList", {"unused": True}))
    invalid_cron_delete = asyncio.run(registry.execute("CronDelete", {"id": cron_id, "unused": True}))
    cron_delete = asyncio.run(registry.execute("CronDelete", {"id": cron_id}))

    assert cron.raw["schedule"]["schedule"] == "0 9 * * *"
    assert cron.raw["schedule"]["input"] == "Check repository health"
    assert cron.raw["schedule"]["metadata"]["recurring"] == "true"
    assert cron.raw["srcOriginCron"]["id"] == cron_id
    assert cron.content == (
        "Scheduled recurring job %s (0 9 * * *). "
        "Session-only (not written to disk, dies when Claude exits). "
        "Auto-expires after 30 days. Use CronDelete to cancel sooner."
    ) % cron_id
    assert cron_list.raw["schedules"][0]["short_id"] == cron_id
    assert cron_list.content == "%s - 0 9 * * * (recurring) [session-only]: Check repository health" % cron_id
    assert invalid_cron_create.is_error is True
    assert "Invalid cron expression 'bad'" in invalid_cron_create.content
    assert invalid_cron_list.raw["details"] == "unexpected argument: unused"
    assert invalid_cron_delete.raw["details"] == "unexpected argument: unused"
    assert cron_delete.raw["deleted"] is True
    assert cron_delete.raw["id"] == cron_id
    assert cron_delete.content == "Cancelled job %s." % cron_id

    invalid_entered = asyncio.run(registry.execute("EnterPlanMode", {"unused": True}))
    entered = asyncio.run(registry.execute("EnterPlanMode", {}))
    exited = asyncio.run(
        registry.execute(
            "ExitPlanMode",
            {
                "plan": "1. Add aliases\n2. Run tests",
                "allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}],
                "planFilePath": ".agents/plans/current.md",
            },
        )
    )
    invalid_exited = asyncio.run(
        registry.execute("ExitPlanMode", {"plan": "1. Bad field", "allowed_prompts": []})
    )
    invalid_reentered = asyncio.run(registry.execute("ExitPlanMode", {"plan": "1. Not in plan mode"}))
    assert entered.raw["mode"] == "plan"
    assert invalid_entered.raw["details"] == "unexpected argument: unused"
    assert exited.raw["mode"] == "default"
    assert exited.raw["allowedPrompts"] == [{"tool": "Bash", "prompt": "run tests"}]
    assert exited.raw["filePath"] == ".agents/plans/current.md"
    assert "User has approved your plan. You can now start coding." in exited.content
    assert "## Approved Plan:" in exited.content
    assert context.plan_text == "1. Add aliases\n2. Run tests"
    assert invalid_exited.raw["details"] == "unexpected argument: allowed_prompts"
    assert invalid_reentered.content == "not in plan mode"

    specs = {
        spec.name: spec.raw["metadata"]
        for spec in registry.specs(
            [
                "TaskCreate",
                "TaskList",
                "TaskGet",
                "TaskUpdate",
                "CronCreate",
                "CronList",
                "CronDelete",
                "ToolSearch",
                "EnterPlanMode",
                "ExitPlanMode",
            ]
        )
    }
    assert {name: metadata["alias_of"] for name, metadata in specs.items()} == {
        "TaskCreate": "task.create",
        "TaskList": "task.list",
        "TaskGet": "task.get",
        "TaskUpdate": "task.update",
        "CronCreate": "schedule.create",
        "CronList": "schedule.list",
        "CronDelete": "schedule.delete",
        "ToolSearch": "tool.search",
        "EnterPlanMode": "plan.enter",
        "ExitPlanMode": "plan.exit",
    }
    assert specs["TaskCreate"]["defer"] is True
    assert specs["TaskList"]["defer"] is True
    assert specs["TaskGet"]["defer"] is True
    assert specs["TaskUpdate"]["defer"] is True
    assert specs["CronCreate"]["defer"] is True
    assert specs["CronList"]["defer"] is True
    assert specs["CronDelete"]["defer"] is True
    assert specs["ToolSearch"]["defer"] is True
    assert specs["EnterPlanMode"]["defer"] is True
    assert specs["ExitPlanMode"]["defer"] is True
    assert specs["EnterPlanMode"]["max_result_size_chars"] == 100000
    assert specs["ExitPlanMode"]["max_result_size_chars"] == 100000

    impact = describe_tool_impact(
        ToolCall(
            id="call-task-update",
            name="TaskUpdate",
            arguments={"taskId": short_id, "subject": "Done", "status": "completed"},
        )
    )
    assert impact.tool_name == "task.update"
    assert impact.summary == "set task %s to completed" % short_id


def test_builtin_task_run_executes_tracked_task_with_child_session(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    ran = asyncio.run(
        registry.execute(
            "task.run",
            {"title": "Run tracked work", "input": "do the work", "step_name": "implement"},
        )
    )
    steps = asyncio.run(store.list_steps(ran.raw["task"]["task_id"]))

    assert ran.is_error is False
    assert ran.raw["task"]["status"] == "finished"
    assert ran.raw["step"]["name"] == "implement"
    assert ran.raw["step"]["output"] == "executed: do the work"
    assert ran.raw["run"]["status"] == "finished"
    assert ran.raw["result"]["content"] == "executed: do the work"
    assert steps[0].status == TaskStepStatus.SUCCEEDED
    assert created_children[0][1] == ran.raw["task"]["task_id"]

    impact = describe_tool_impact(ToolCall(id="call-task-run", name="task.run", arguments={"title": "Run tracked work", "input": "do the work"}))
    assert impact.risk == "high"
    assert impact.operations == ["task_state_write", "subagent"]
    assert "do the work" in impact.diff_preview


def test_builtin_task_background_runs_tracked_task_asynchronously(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            await asyncio.sleep(0)
            return AgentResult(
                content="background: %s" % text,
                messages=[Message.from_text("assistant", "background")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "background"})],
            )

    async def create_child(child_spec, task_id=""):
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        started = await registry.execute("task.background", {"title": "Run async", "input": "background work"})
        task_id = started.raw["task"]["task_id"]
        await context.background_tasks[task_id]
        backgrounds = await registry.execute("task.backgrounds", {})
        output = await registry.execute("task.output", {"task_id": task_id})
        return started, backgrounds, output

    started, backgrounds, output = asyncio.run(execute())

    assert started.raw["background"] == {"running": True, "done": False}
    assert backgrounds.raw["background_tasks"][0]["done"] is True
    assert backgrounds.raw["background_tasks"][0]["result"]["status"] == "finished"
    assert "background: background work" in output.raw["output"]

    impact = describe_tool_impact(ToolCall(id="call-bg", name="task.background", arguments={"title": "Run async", "input": "background work"}))
    assert impact.risk == "high"
    assert impact.operations == ["task_state_write", "subagent"]


def test_builtin_schedule_tools_manage_reusable_task_definitions(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "schedule.create",
            {"title": "Daily repo check", "schedule": "0 9 * * *", "input": "Check repository health"},
        )
    )
    short_id = created.raw["schedule"]["short_id"]
    listed = asyncio.run(registry.execute("schedule.list", {}))
    ran = asyncio.run(registry.execute("schedule.run", {"schedule_id": short_id, "background": False}))
    deleted = asyncio.run(registry.execute("schedule.delete", {"schedule_id": short_id}))

    task = asyncio.run(store.load_task(ran.raw["task"]["task_id"]))
    assert created.is_error is False
    assert listed.raw["schedules"][0]["short_id"] == short_id
    assert ran.raw["schedule"]["last_run_task_id"] == ran.raw["task"]["task_id"]
    assert ran.raw["task"]["metadata"]["source"] == "schedule"
    assert ran.raw["task"]["metadata"]["schedule_id"] == created.raw["schedule"]["schedule_id"]
    assert task is not None
    assert task.title == "Daily repo check"
    assert deleted.raw["deleted"] is True
    assert asyncio.run(registry.execute("schedule.list", {})).raw["schedules"] == []

    impact = describe_tool_impact(ToolCall(id="call-schedule", name="schedule.run", arguments={"schedule_id": short_id}))
    assert impact.risk == "high"
    assert impact.operations == ["schedule_run", "task_state_write", "subagent"]


def test_builtin_schedule_tools_use_shared_schedule_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    schedule_store = InMemoryScheduleStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            schedule_store=schedule_store,
            agent_spec=spec,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        created = await first.execute(
            "schedule.create",
            {"title": "Daily repo check", "schedule": "0 9 * * *", "input": "Check repository health"},
        )
        listed = await second.execute("schedule.list", {})
        deleted = await second.execute("schedule.delete", {"schedule_id": created.raw["schedule"]["short_id"]})
        after_delete = await first.execute("schedule.list", {})
        return created, listed, deleted, after_delete

    created, listed, deleted, after_delete = asyncio.run(execute())

    assert listed.raw["schedules"][0]["schedule_id"] == created.raw["schedule"]["schedule_id"]
    assert deleted.raw["deleted"] is True
    assert after_delete.raw["schedules"] == []


def test_builtin_workflow_tools_validate_and_run_task_agent_nodes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    nodes = [
        {"node_id": "plan", "kind": "task", "name": "Plan", "input": "write plan"},
        {"node_id": "review", "kind": "agent", "name": "Review", "prompt": "review plan", "agent_id": "reviewer"},
    ]
    edges = [{"source": "plan", "target": "review"}]

    validated = asyncio.run(registry.execute("workflow.validate", {"workflow_id": "wf-1", "nodes": nodes, "edges": edges}))
    ran = asyncio.run(registry.execute("workflow.run", {"workflow_id": "wf-1", "nodes": nodes, "edges": edges}))
    tasks = asyncio.run(store.list_tasks("tenant", user_id="user", agent_id="agent"))

    assert validated.raw["order"] == ["plan", "review"]
    assert ran.raw["status"] == "finished"
    assert [result["node_id"] for result in ran.raw["results"]] == ["plan", "review"]
    assert ran.raw["results"][0]["content"] == "executed: write plan"
    assert ran.raw["results"][1]["content"] == "executed: review plan"
    assert tasks[0].metadata["workflow_node_id"] == "plan"
    assert created_children[0][1] == tasks[0].task_id
    assert created_children[1][0].agent_id == "reviewer"

    impact = describe_tool_impact(ToolCall(id="call-workflow", name="workflow.run", arguments={"nodes": nodes}))
    assert impact.risk == "high"
    assert impact.operations == ["workflow_run", "subagent"]


def test_builtin_workflow_tools_manage_saved_workflows(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    nodes = [
        {"node_id": "draft", "kind": "task", "name": "Draft", "input": "draft release plan"},
        {
            "node_id": "review",
            "kind": "agent",
            "name": "Review",
            "prompt": "review release plan",
            "agent_id": "reviewer",
            "system_prompt": "Be terse.",
        },
    ]
    edges = [{"source": "draft", "target": "review"}]

    saved = asyncio.run(
        registry.execute(
            "workflow.save",
            {
                "name": "release-plan",
                "workflow_id": "release",
                "nodes": nodes,
                "edges": edges,
                "metadata": {"scope": "release"},
            },
        )
    )
    listed = asyncio.run(registry.execute("workflow.templates", {"query": "release"}))
    read = asyncio.run(registry.execute("workflow.read", {"name": "release-plan"}))
    ran = asyncio.run(registry.execute("workflow.run_saved", {"name": "release-plan"}))
    deleted = asyncio.run(registry.execute("workflow.delete", {"name": "release-plan"}))

    assert saved.raw["path"] == ".agents/workflows/release-plan.json"
    assert saved.raw["workflow"]["node_count"] == 2
    assert listed.raw["workflows"][0]["workflow_id"] == "release"
    assert read.raw["workflow"]["nodes"][1]["system_prompt"] == "Be terse."
    assert ran.raw["status"] == "finished"
    assert [result["node_id"] for result in ran.raw["results"]] == ["draft", "review"]
    assert ran.raw["results"][0]["content"] == "executed: draft release plan"
    assert ran.raw["results"][1]["content"] == "executed: review release plan"
    assert created_children[1][0].agent_id == "reviewer"
    assert deleted.raw["deleted"] is True

    run_impact = describe_tool_impact(ToolCall(id="call-workflow", name="workflow.run_saved", arguments={"name": "release-plan"}))
    save_impact = describe_tool_impact(ToolCall(id="call-workflow-save", name="workflow.save", arguments={"name": "release-plan", "nodes": nodes}))
    assert run_impact.risk == "high"
    assert run_impact.operations == ["workflow_run", "subagent"]
    assert run_impact.paths == [".agents/workflows/release-plan.json"]
    assert save_impact.risk == "medium"
    assert save_impact.operations == ["workflow_write"]
    assert save_impact.writes_files is True


def test_builtin_planning_tools_manage_todos_and_plan_mode(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    todos = [
        {"content": "Inspect runtime", "status": "completed", "activeForm": "Inspecting runtime"},
        {"content": "Add planning tools", "status": "in_progress", "activeForm": "Adding planning tools"},
        {"content": "Run checks", "status": "pending", "activeForm": "Running checks"},
    ]
    todo_contract = registry.describe_call("todo.write", {"todos": todos})
    written = asyncio.run(registry.execute("todo.write", {"todos": todos}))
    read = asyncio.run(registry.execute("todo.read", {}))
    entered = asyncio.run(registry.execute("plan.enter", {}))
    exited = asyncio.run(
        registry.execute(
            "plan.exit",
            {
                "plan": "1. Add tools\n2. Test runtime",
                "allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}],
            },
        )
    )
    status = asyncio.run(registry.execute("plan.status", {}))

    assert written.is_error is False
    assert written.content == (
        "Todos have been modified successfully. "
        "Ensure that you continue to use the todo list to track your progress. "
        "Please proceed with the current tasks if applicable"
    )
    assert written.raw["newTodos"][1]["activeForm"] == "Adding planning tools"
    assert written.raw["verificationNudgeNeeded"] is False
    assert todo_contract["metadata"]["defer"] is True
    assert todo_contract["activity"]["kind"] == "state"
    assert read.raw["summary"] == {"pending": 1, "in_progress": 1, "completed": 1}
    assert entered.raw["mode"] == "plan"
    assert exited.raw["mode"] == "default"
    assert exited.raw["allowedPrompts"] == [{"tool": "Bash", "prompt": "run tests"}]
    assert status.raw["mode"] == "default"
    assert status.raw["plan"] == "1. Add tools\n2. Test runtime"

    impact = describe_tool_impact(
        ToolCall(id="call-plan", name="plan.exit", arguments={"plan": "1. Add tools\n2. Test runtime"})
    )
    assert impact.risk == "medium"
    assert impact.operations == ["plan_state_write"]
    assert "Add tools" in impact.diff_preview

    cleared = asyncio.run(
        registry.execute(
            "todo.write",
            {"todos": [{"content": "Run checks", "status": "completed", "activeForm": "Running checks"}]},
        )
    )
    assert cleared.raw["cleared"] is True
    assert context.todos == []

    empty = asyncio.run(registry.execute("todo.write", {"todos": []}))
    assert empty.raw["cleared"] is True

    unexpected = asyncio.run(registry.execute("todo.write", {"todos": [], "extra": True}))
    assert unexpected.is_error is True
    assert unexpected.raw["details"] == "unexpected argument: extra"


def test_builtin_planning_tools_persist_session_state(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def run():
        await registry.execute(
            "todo.write",
            {
                "todos": [
                    {"content": "Persist planning state", "status": "in_progress", "activeForm": "Persisting planning state"},
                ]
            },
        )
        await registry.execute("plan.enter", {})
        await registry.execute("plan.exit", {"plan": "Persist todo and plan state."})
        return await store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace")

    record = asyncio.run(run())

    assert record is not None
    assert record.todos[0]["content"] == "Persist planning state"
    assert record.plan_mode is False
    assert record.plan_text == "Persist todo and plan state."


def test_builtin_meta_tools_search_tools_and_discover_skills(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "version": "1.0.0",
                "description": "Focus on repo-specific implementation work.",
                "tools": ["filesystem.read"],
                "prompt_fragments": ["prompts/focus.md"],
            }
        ),
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / "prompt.md").write_text("Use planner plugin guidance.", encoding="utf-8")
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "planner",
                "version": "1.0.0",
                "description": "Planning plugin",
                "tools": ["todo.write"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    skill_registry = SkillRegistry.load(SkillLoader(tmp_path), ["focus"])
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=skill_registry,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    context.enabled_tools = ["tool.search", "skill.discover", "plugin.discover", "filesystem.read"]

    tools = asyncio.run(registry.execute("tool.search", {"query": "file read", "include_all": False}))
    skills = asyncio.run(registry.execute("skill.discover", {"query": "focus", "include_prompt": True}))
    plugins = asyncio.run(registry.execute("plugin.discover", {"query": "planner", "include_prompt": True}))

    assert tools.is_error is False
    assert tools.raw["matches"][0]["name"] == "filesystem.read"
    assert tools.raw["matches"][0]["enabled"] is True
    assert skills.raw["skills"][0]["name"] == "focus"
    assert skills.raw["skills"][0]["enabled"] is True
    assert skills.raw["skills"][0]["prompt_fragments"] == ["prompts/focus.md"]
    assert plugins.raw["plugins"][0]["name"] == "planner"
    assert plugins.raw["plugins"][0]["tools"] == ["todo.write"]
    assert plugins.raw["plugins"][0]["prompts"] == [{"path": "prompt.md", "content": "Use planner plugin guidance."}]


def test_builtin_plugin_tools_install_and_uninstall_local_plugins(tmp_path: Path):
    source_dir = tmp_path / "plugin-source"
    (source_dir / ".codex-plugin").mkdir(parents=True)
    (source_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "helper",
                "version": "1.0.0",
                "description": "Helper plugin",
                "tools": ["filesystem.read"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    installed = asyncio.run(registry.execute("plugin.install", {"source": str(source_dir)}))
    discovered = asyncio.run(registry.execute("plugin.discover", {"query": "helper"}))
    uninstalled = asyncio.run(registry.execute("plugin.uninstall", {"name": "helper"}))

    assert installed.raw["installed"] is True
    assert installed.raw["plugin"]["name"] == "helper"
    assert discovered.raw["plugins"][0]["name"] == "helper"
    assert uninstalled.raw == {"plugin": "helper", "uninstalled": True}
    assert not (tmp_path / ".agents" / "plugins" / "helper").exists()

    impact = describe_tool_impact(ToolCall(id="call-plugin", name="plugin.install", arguments={"source": str(source_dir)}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]
    assert impact.writes_files is True


def test_builtin_skill_tools_install_and_uninstall_skill_packages(tmp_path: Path):
    source_dir = tmp_path / "skill-source"
    source_dir.mkdir()
    (source_dir / "prompt.md").write_text("Use installed skill guidance.", encoding="utf-8")
    (source_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "installed",
                "version": "1.0.0",
                "description": "Installed skill",
                "tools": ["filesystem.read"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=SkillRegistry([]),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    installed = asyncio.run(registry.execute("skill.install", {"source": str(source_dir)}))
    discovered = asyncio.run(registry.execute("skill.discover", {"query": "installed", "include_prompt": True}))
    loaded = SkillLoader(tmp_path).load("installed")
    uninstalled = asyncio.run(registry.execute("skill.uninstall", {"name": "installed"}))

    assert installed.raw["installed"] is True
    assert installed.raw["skill"]["name"] == "installed"
    assert discovered.raw["skills"][0]["name"] == "installed"
    assert discovered.raw["skills"][0]["prompt_fragments"] == ["prompt.md"]
    assert loaded.prompt_fragments == ["Use installed skill guidance."]
    assert uninstalled.raw == {"skill": "installed", "uninstalled": True}
    assert not (tmp_path / "skills" / "installed").exists()

    impact = describe_tool_impact(ToolCall(id="call-skill-install", name="skill.install", arguments={"source": str(source_dir)}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]
    assert impact.writes_files is True


def test_builtin_prompt_template_tools_manage_local_templates(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    saved = asyncio.run(registry.execute("prompt.save", {"name": "reviewer", "content": "Review {arguments} for {{focus}}."}))
    templates = asyncio.run(registry.execute("prompt.templates", {"query": "review"}))
    read = asyncio.run(registry.execute("prompt.read", {"name": "reviewer"}))
    rendered = asyncio.run(
        registry.execute(
            "prompt.render",
            {"name": "reviewer", "raw_arguments": "src/agents", "arguments": {"focus": "regressions"}},
        )
    )
    deleted = asyncio.run(registry.execute("prompt.delete", {"name": "reviewer"}))

    assert saved.raw["path"] == ".agents/prompts/reviewer.md"
    assert templates.raw["templates"][0]["name"] == "reviewer"
    assert read.raw["content"] == "Review {arguments} for {{focus}}."
    assert rendered.raw["prompt"] == "Review src/agents for regressions."
    assert deleted.raw["deleted"] is True

    impact = describe_tool_impact(ToolCall(id="call-prompt", name="prompt.save", arguments={"name": "reviewer", "content": "Review carefully."}))
    assert impact.risk == "medium"
    assert impact.operations == ["prompt_write"]
    assert impact.paths == [".agents/prompts/reviewer.md"]


def test_builtin_session_context_tools_inspect_and_compact_session(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    runtime = SimpleNamespace(protocol="scripted", model="test-model", enabled_tools=["session.status", "context.messages"])
    trace_item = SimpleNamespace(
        id="system.user_configured",
        layer=SimpleNamespace(value="system"),
        source="settings",
        priority=100,
        tokens=3,
        included=True,
        text="Base prompt.",
    )
    session = AgentSession(
        runtime=runtime,
        system_prompt="Base prompt.",
        max_context_tokens=1000,
        context_trace=[trace_item],
        workspace=workspace,
        tool_context=context,
    )
    session.messages.append(Message.from_text("user", "hello"))

    status = asyncio.run(registry.execute("session.status", {}))
    summary = asyncio.run(registry.execute("session.summary", {"max_messages": 2}))
    trace = asyncio.run(registry.execute("context.trace", {"include_text": True}))
    messages = asyncio.run(registry.execute("context.messages", {"include_system": True}))
    exported = asyncio.run(registry.execute("session.export", {"path": "exports/session.json", "include_system": True}))
    rewound = asyncio.run(registry.execute("context.rewind", {"drop_last": 1}))
    compacted = asyncio.run(registry.execute("context.compact", {"target_tokens": 100}))

    assert context.session is session
    assert status.raw["model"] == {"protocol": "scripted", "model": "test-model"}
    assert status.raw["messages"]["non_system"] == 1
    assert "user: hello" in summary.raw["summary"]
    assert summary.raw["roles"] == {"user": 1}
    assert trace.raw["items"][0]["text"] == "Base prompt."
    assert messages.raw["messages"][0]["role"] == "system"
    assert exported.raw["path"] == "exports/session.json"
    assert "hello" in (tmp_path / "exports" / "session.json").read_text(encoding="utf-8")
    assert rewound.raw["dropped_messages"] == 1
    assert [message.role for message in session.messages] == ["system"]
    assert compacted.raw["before_messages"] >= compacted.raw["after_messages"]

    impact = describe_tool_impact(ToolCall(id="call-context", name="context.compact", arguments={}))
    assert impact.risk == "medium"
    assert impact.operations == ["context_write"]
    summary_impact = describe_tool_impact(ToolCall(id="call-summary", name="session.summary", arguments={}))
    assert summary_impact.risk == "low"
    assert summary_impact.operations == ["context_read"]
    export_impact = describe_tool_impact(ToolCall(id="call-export", name="session.export", arguments={"path": "exports/session.json"}))
    assert export_impact.risk == "medium"
    assert export_impact.operations == ["session_export"]
    assert export_impact.writes_files is True


def test_builtin_permission_tools_report_status_and_explain_decisions(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["shell.run"],
        approval_required_tools=["shell.run"],
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
    )
    context.enabled_tools = ["shell.run"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    status = asyncio.run(registry.execute("permission.status", {}))
    sources = asyncio.run(registry.execute("permission.sources", {}))
    explained = asyncio.run(
        registry.execute(
            "permission.explain",
            {"tool": "shell.run", "arguments": {"command": "pytest -q"}},
        )
    )

    assert status.raw["profile"] == "auto"
    assert status.raw["approval_required_tools"] == ["shell.run"]
    assert status.raw["rules_by_source"]["agent_spec"]["ask"] == ["shell.run"]
    assert sources.raw["rules_by_source"]["agent_spec"]["ask"] == ["shell.run"]
    assert sources.raw["rules"][0] == {"source": "agent_spec", "behavior": "ask", "tool": "shell.run"}
    assert explained.raw["decision"]["requires_approval"] is True
    assert explained.raw["decision"]["metadata"]["source"] == "agent_spec"
    assert explained.raw["decision"]["metadata"]["rule"] == "ask"
    assert explained.raw["impact"]["risk"] == "high"
    assert explained.raw["impact"]["commands"] == ["pytest -q"]

    deny_result = asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "shell.run"}))
    denied = asyncio.run(registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "pytest -q"}}))
    allow_result = asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "filesystem.read"}))
    remove_allow = asyncio.run(registry.execute("permission.remove_rule", {"behavior": "allow", "tool": "filesystem.read"}))
    remove_deny = asyncio.run(registry.execute("permission.remove_rule", {"tool": "shell.run"}))
    rule_impact = describe_tool_impact(
        ToolCall(id="call-permission", name="permission.add_rule", arguments={"behavior": "deny", "tool": "shell.run"})
    )

    assert deny_result.raw["status"]["denied_tools"] == ["shell.run"]
    assert deny_result.raw["status"]["approval_required_tools"] == []
    assert denied.raw["decision"]["allowed"] is False
    assert denied.raw["decision"]["metadata"]["rule"] == "deny"
    assert allow_result.raw["status"]["restrict_allowed_tools"] is True
    assert allow_result.raw["status"]["allowed_tools"] == ["filesystem.read"]
    assert remove_allow.raw["status"]["restrict_allowed_tools"] is False
    assert remove_deny.raw["removed"] == [{"behavior": "deny", "tool": "shell.run"}]
    assert rule_impact.operations == ["permission_write"]


def test_builtin_permission_rules_match_bash_command_patterns(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["shell.run"],
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
    )
    context.enabled_tools = ["shell.run"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    added = asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "Bash(git *)"}))
    env_git = asyncio.run(
        registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "FOO=bar git status"}})
    )
    compound_git = asyncio.run(
        registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "npm test && git status"}})
    )
    npm = asyncio.run(registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "npm test"}}))
    echo = asyncio.run(registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "echo git status"}}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "Bash(npm install:*)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "Bash(rm:*)"}))
    timeout_install = asyncio.run(
        registry.execute(
            "permission.explain",
            {"tool": "shell.run", "arguments": {"command": "timeout 10 npm install left-pad"}},
        )
    )
    xargs_rm = asyncio.run(
        registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "printf x | xargs rm -f"}})
    )
    flagged_xargs_rm = asyncio.run(
        registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "printf x | xargs -n1 rm -f"}})
    )
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "ask", "tool": "Bash(npm publish:*)"}))
    wrapped_publish = asyncio.run(
        registry.execute(
            "permission.explain",
            {"tool": "shell.run", "arguments": {"command": "nice -n 5 FOO=bar timeout 10 npm publish --dry-run"}},
        )
    )
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "ask", "tool": "Bash(npm:*)"}))
    npm_ask = asyncio.run(registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "npm test"}}))

    assert added.raw["status"]["denied_tools"] == ["Bash(git *)"]
    assert env_git.raw["decision"]["allowed"] is False
    assert env_git.raw["decision"]["metadata"]["matched_rule"] == "Bash(git *)"
    assert compound_git.raw["decision"]["allowed"] is False
    assert npm.raw["decision"]["allowed"] is True
    assert echo.raw["decision"]["allowed"] is True
    assert timeout_install.raw["decision"]["allowed"] is False
    assert timeout_install.raw["decision"]["metadata"]["matched_rule"] == "Bash(npm install:*)"
    assert xargs_rm.raw["decision"]["allowed"] is False
    assert xargs_rm.raw["decision"]["metadata"]["matched_rule"] == "Bash(rm:*)"
    assert flagged_xargs_rm.raw["decision"]["allowed"] is True
    assert wrapped_publish.raw["decision"]["requires_approval"] is True
    assert wrapped_publish.raw["decision"]["metadata"]["matched_rule"] == "Bash(npm publish:*)"
    assert npm_ask.raw["decision"]["requires_approval"] is True
    assert npm_ask.raw["decision"]["metadata"]["matched_rule"] == "Bash(npm:*)"


def test_bash_allow_rules_only_strip_safe_env_prefixes():
    allow_policy = StaticToolPermissionPolicy(
        allowed_tools=["Bash(npm test:*)", "Bash(docker ps:*)"],
    )

    safe_env = asyncio.run(
        allow_policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": "NODE_ENV=prod npm test -- --watch"},
            )
        )
    )
    unsafe_env = asyncio.run(
        allow_policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": "DOCKER_HOST=tcp://evil.invalid docker ps"},
            )
        )
    )
    wrapper_env = asyncio.run(
        allow_policy.authorize(
            ToolCall(
                id="3",
                name="shell.run",
                arguments={"command": "nice FOO=bar npm test -- --watch"},
            )
        )
    )

    deny_policy = StaticToolPermissionPolicy(denied_tools=["Bash(docker ps:*)"])
    denied_unsafe_env = asyncio.run(
        deny_policy.authorize(
            ToolCall(
                id="4",
                name="shell.run",
                arguments={"command": "DOCKER_HOST=tcp://evil.invalid docker ps"},
            )
        )
    )

    assert safe_env.allowed is True
    assert safe_env.metadata["matched_rule"] == "Bash(npm test:*)"
    assert unsafe_env.allowed is False
    assert unsafe_env.metadata["rule"] == "allowlist"
    assert wrapper_env.allowed is False
    assert wrapper_env.metadata["rule"] == "allowlist"
    assert denied_unsafe_env.allowed is False
    assert denied_unsafe_env.metadata["matched_rule"] == "Bash(docker ps:*)"


def test_bash_permission_rules_strip_simple_output_redirections_for_matching():
    policy = StaticToolPermissionPolicy(
        allowed_tools=["Bash(python script.py)", "Bash(echo hi)"],
    )

    separated_stdout = asyncio.run(
        policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": "python script.py > out.txt"},
            )
        )
    )
    fused_stdout = asyncio.run(
        policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": "python script.py >out.txt"},
            )
        )
    )
    stdout_append = asyncio.run(
        policy.authorize(
            ToolCall(
                id="3",
                name="shell.run",
                arguments={"command": "python script.py 1>>logs/out.txt"},
            )
        )
    )
    combined_stdout_stderr = asyncio.run(
        policy.authorize(
            ToolCall(
                id="4",
                name="shell.run",
                arguments={"command": "python script.py &> out.txt"},
            )
        )
    )
    dynamic_target = asyncio.run(
        policy.authorize(
            ToolCall(
                id="5",
                name="shell.run",
                arguments={"command": "python script.py > $OUT"},
            )
        )
    )
    quoted_argument = asyncio.run(
        policy.authorize(
            ToolCall(
                id="6",
                name="shell.run",
                arguments={"command": 'echo "hi > out.txt"'},
            )
        )
    )

    assert separated_stdout.allowed is True
    assert separated_stdout.metadata["matched_rule"] == "Bash(python script.py)"
    assert fused_stdout.allowed is True
    assert stdout_append.allowed is True
    assert combined_stdout_stderr.allowed is True
    assert dynamic_target.allowed is False
    assert dynamic_target.metadata["rule"] == "allowlist"
    assert quoted_argument.allowed is False
    assert quoted_argument.metadata["rule"] == "allowlist"


def test_bash_literal_permission_rules_still_match_output_redirections():
    policy = StaticToolPermissionPolicy(
        allowed_tools=["Bash(python script.py > out.txt)"],
    )

    exact_redirect = asyncio.run(
        policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": "python script.py > out.txt"},
            )
        )
    )
    no_redirect = asyncio.run(
        policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": "python script.py"},
            )
        )
    )

    assert exact_redirect.allowed is True
    assert exact_redirect.metadata["matched_rule"] == "Bash(python script.py > out.txt)"
    assert no_redirect.allowed is False
    assert no_redirect.metadata["rule"] == "allowlist"


def test_bash_allow_prefix_rules_reject_operator_bearing_candidates():
    allow_policy = StaticToolPermissionPolicy(allowed_tools=["Bash(cd:*)", "Bash(echo *)"])
    escaped_prefix_compound = asyncio.run(
        allow_policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": r"cd src\&\& python3 hello.py"},
            )
        )
    )
    escaped_wildcard_compound = asyncio.run(
        allow_policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": r"echo ok\|cat secrets.txt"},
            )
        )
    )

    deny_policy = StaticToolPermissionPolicy(denied_tools=["Bash(cd:*)"])
    denied_escaped_compound = asyncio.run(
        deny_policy.authorize(
            ToolCall(
                id="3",
                name="shell.run",
                arguments={"command": r"cd src\&\& python3 hello.py"},
            )
        )
    )

    assert escaped_prefix_compound.allowed is False
    assert escaped_prefix_compound.metadata["rule"] == "allowlist"
    assert escaped_wildcard_compound.allowed is False
    assert escaped_wildcard_compound.metadata["rule"] == "allowlist"
    assert denied_escaped_compound.allowed is False
    assert denied_escaped_compound.metadata["matched_rule"] == "Bash(cd:*)"


def test_bash_allow_rules_require_every_compound_subcommand_to_match():
    partial_policy = StaticToolPermissionPolicy(allowed_tools=["Bash(npm:*)"])
    partial = asyncio.run(
        partial_policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": "npm test && git status"},
            )
        )
    )

    full_policy = StaticToolPermissionPolicy(allowed_tools=["Bash(npm:*)", "Bash(git:*)"])
    full = asyncio.run(
        full_policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": "npm test && git status"},
            )
        )
    )

    exact_policy = StaticToolPermissionPolicy(allowed_tools=["Bash(npm test && git status)"])
    exact = asyncio.run(
        exact_policy.authorize(
            ToolCall(
                id="3",
                name="shell.run",
                arguments={"command": "npm test && git status"},
            )
        )
    )

    assert partial.allowed is False
    assert partial.metadata["rule"] == "allowlist"
    assert full.allowed is True
    assert full.metadata["matched_rule"] == "Bash(npm:*)"
    assert exact.allowed is True
    assert exact.metadata["matched_rule"] == "Bash(npm test && git status)"


def test_bash_literal_compound_rules_match_full_command_for_deny_and_ask():
    command = "npm test && git status"
    deny_policy = StaticToolPermissionPolicy(
        denied_tools=["Bash(npm test && git status)"],
    )
    ask_policy = StaticToolPermissionPolicy(
        approval_required_tools=["Bash(npm test && git status)"],
    )

    denied = asyncio.run(
        deny_policy.authorize(
            ToolCall(
                id="1",
                name="shell.run",
                arguments={"command": command},
            )
        )
    )
    ask = asyncio.run(
        ask_policy.authorize(
            ToolCall(
                id="2",
                name="shell.run",
                arguments={"command": command},
            )
        )
    )
    subcommand = asyncio.run(
        deny_policy.authorize(
            ToolCall(
                id="3",
                name="shell.run",
                arguments={"command": "npm test"},
            )
        )
    )

    assert denied.allowed is False
    assert denied.metadata["matched_rule"] == "Bash(npm test && git status)"
    assert ask.requires_approval is True
    assert ask.metadata["matched_rule"] == "Bash(npm test && git status)"
    assert subcommand.allowed is True


def test_builtin_permission_rules_match_legacy_path_and_pattern_rules(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["filesystem.read", "filesystem.write", "notebook.edit", "search.grep", "search.glob"],
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
    )
    context.enabled_tools = ["filesystem.read", "filesystem.write", "notebook.edit", "search.grep", "search.glob"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "Read(src/**)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "filesystem.write"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "search.grep"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "Glob(*.py)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "Write(secrets/**)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "MultiEdit(secrets/**)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "NotebookEdit(secrets/**)"}))
    asyncio.run(registry.execute("permission.add_rule", {"behavior": "ask", "tool": "Grep(TODO*)"}))

    read_allowed = asyncio.run(registry.execute("permission.explain", {"tool": "filesystem.read", "arguments": {"path": "src/app.py"}}))
    read_denied = asyncio.run(registry.execute("permission.explain", {"tool": "filesystem.read", "arguments": {"path": "docs/app.py"}}))
    write_denied = asyncio.run(
        registry.execute("permission.explain", {"tool": "filesystem.write", "arguments": {"path": "secrets/token.txt", "content": "x"}})
    )
    grep_ask = asyncio.run(
        registry.execute("permission.explain", {"tool": "search.grep", "arguments": {"pattern": "TODO fix", "path": "src"}})
    )
    grep_allowed = asyncio.run(
        registry.execute("permission.explain", {"tool": "search.grep", "arguments": {"pattern": "FIXME", "path": "src"}})
    )
    glob_allowed = asyncio.run(
        registry.execute("permission.explain", {"tool": "search.glob", "arguments": {"pattern": "*.py", "path": "src"}})
    )
    multi_edit_denied = asyncio.run(
        registry.execute(
            "permission.explain",
            {
                "tool": "MultiEdit",
                "arguments": {
                    "file_path": "secrets/config.py",
                    "edits": [{"old_string": "old", "new_string": "new"}],
                },
            },
        )
    )
    notebook_denied = asyncio.run(
        registry.execute(
            "permission.explain",
            {"tool": "notebook.edit", "arguments": {"notebook_path": "secrets/analysis.ipynb", "cell_id": "cell-0", "new_source": "x"}},
        )
    )

    assert read_allowed.raw["decision"]["allowed"] is True
    assert read_allowed.raw["decision"]["metadata"]["matched_rule"] == "Read(src/**)"
    assert read_denied.raw["decision"]["allowed"] is False
    assert read_denied.raw["decision"]["metadata"]["rule"] == "allowlist"
    assert write_denied.raw["decision"]["allowed"] is False
    assert write_denied.raw["decision"]["metadata"]["matched_rule"] == "Write(secrets/**)"
    assert grep_ask.raw["decision"]["requires_approval"] is True
    assert grep_ask.raw["decision"]["metadata"]["matched_rule"] == "Grep(TODO*)"
    assert grep_allowed.raw["decision"]["allowed"] is True
    assert grep_allowed.raw["decision"]["metadata"]["matched_rule"] == "search.grep"
    assert glob_allowed.raw["decision"]["allowed"] is True
    assert glob_allowed.raw["decision"]["metadata"]["matched_rule"] == "Glob(*.py)"
    assert multi_edit_denied.raw["decision"]["allowed"] is False
    assert multi_edit_denied.raw["decision"]["metadata"]["matched_rule"] == "MultiEdit(secrets/**)"
    assert notebook_denied.raw["decision"]["allowed"] is False
    assert notebook_denied.raw["decision"]["metadata"]["matched_rule"] == "NotebookEdit(secrets/**)"


def test_permission_rules_match_src_origin_state_tool_targets():
    policy = StaticToolPermissionPolicy(
        denied_tools=[
            "Read(src/**)",
            "Write(secrets/**)",
            "Edit(secrets/**)",
            "NotebookEdit(notebooks/**)",
            "LSP(src/**)",
            "TaskUpdate(task-*)",
            "TaskOutput(shell-*)",
            "CronDelete(nightly*)",
            "Agent(research*)",
            "SendMessage(teammate*)",
            "TeamCreate(platform*)",
            "WebFetch(https://docs.example/*)",
            "ReadMcpResourceTool(file://docs/*)",
            "mcp__docs",
        ],
        approval_required_tools=[
            "ToolSearch(worktree*)",
            "ListMcpResourcesTool(docs)",
            "ExitWorktree(remove)",
        ],
    )

    cases = [
        ("Read", {"file_path": "src/app.py"}, "Read(src/**)", False),
        ("Write", {"file_path": "secrets/token.txt", "content": "x"}, "Write(secrets/**)", False),
        (
            "Edit",
            {"file_path": "secrets/token.txt", "old_string": "old", "new_string": "new"},
            "Edit(secrets/**)",
            False,
        ),
        (
            "NotebookEdit",
            {"notebook_path": "notebooks/analysis.ipynb", "cell_id": "cell-0", "new_source": "x"},
            "NotebookEdit(notebooks/**)",
            False,
        ),
        ("LSP", {"operation": "hover", "filePath": "src/app.py", "line": 1, "character": 1}, "LSP(src/**)", False),
        ("TaskUpdate", {"taskId": "task-123", "status": "finished"}, "TaskUpdate(task-*)", False),
        ("TaskOutput", {"task_id": "shell-abc"}, "TaskOutput(shell-*)", False),
        ("CronDelete", {"id": "nightly-build"}, "CronDelete(nightly*)", False),
        ("Agent", {"subagent_type": "researcher", "description": "Investigate"}, "Agent(research*)", False),
        ("SendMessage", {"to": "teammate-a", "message": "status"}, "SendMessage(teammate*)", False),
        ("TeamCreate", {"team_name": "platform-core"}, "TeamCreate(platform*)", False),
        ("WebFetch", {"url": "https://docs.example/page", "prompt": "extract"}, "WebFetch(https://docs.example/*)", False),
        ("ReadMcpResourceTool", {"server": "docs", "uri": "file://docs/readme"}, "ReadMcpResourceTool(file://docs/*)", False),
        ("mcp__docs__search", {"query": "agents"}, "mcp__docs", False),
        ("ToolSearch", {"query": "worktree tools"}, "ToolSearch(worktree*)", True),
        ("ListMcpResourcesTool", {"server": "docs"}, "ListMcpResourcesTool(docs)", True),
        ("ExitWorktree", {"action": "remove"}, "ExitWorktree(remove)", True),
    ]

    for tool_name, arguments, matched_rule, requires_approval in cases:
        decision = asyncio.run(policy.authorize(ToolCall(id="call-%s" % tool_name, name=tool_name, arguments=arguments)))
        assert decision.requires_approval is requires_approval
        assert decision.allowed is False
        assert decision.metadata["matched_rule"] == matched_rule


def test_builtin_hook_tools_manage_session_hooks(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    events = asyncio.run(registry.execute("hook.events", {}))
    added = asyncio.run(
        registry.execute(
            "hook.add",
            {
                "event": "pre_tool_use",
                "name": "block-shell",
                "action": "deny_tool",
                "content": "Shell blocked.",
                "tool": "shell.run",
            },
        )
    )
    short_id = added.raw["hook"]["short_id"]
    listed = asyncio.run(registry.execute("hook.list", {}))
    deleted = asyncio.run(registry.execute("hook.delete", {"hook_id": short_id}))

    assert events.raw["events"] == ["before_request", "after_response", "pre_tool_use", "post_tool_use"]
    assert added.raw["hook"]["metadata"]["source"] == "tool"
    assert added.raw["hook"]["tool"] == "shell.run"
    assert added.raw["hook"]["metadata"]["tool"] == "shell.run"
    assert listed.raw["hooks"][0]["short_id"] == short_id
    assert deleted.raw["deleted"] is True
    assert asyncio.run(registry.execute("hook.list", {})).raw["hooks"] == []

    impact = describe_tool_impact(ToolCall(id="call-hook", name="hook.add", arguments={"event": "before_request", "action": "append_system"}))
    assert impact.risk == "medium"
    assert impact.operations == ["hook_state_write"]


def test_builtin_hook_tools_use_shared_hook_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    hook_store = InMemoryHookStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            hook_store=hook_store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        added = await first.execute(
            "hook.add",
            {"event": "pre_tool_use", "name": "block-shell", "action": "deny_tool", "tool": "shell.run", "content": "blocked"},
        )
        listed = await second.execute("hook.list", {})
        deleted = await second.execute("hook.delete", {"hook_id": added.raw["hook"]["short_id"]})
        after_delete = await first.execute("hook.list", {})
        return added, listed, deleted, after_delete

    added, listed, deleted, after_delete = asyncio.run(execute())

    assert listed.raw["hooks"][0]["hook_id"] == added.raw["hook"]["hook_id"]
    assert listed.raw["hooks"][0]["tool"] == "shell.run"
    assert deleted.raw["deleted"] is True
    assert after_delete.raw["hooks"] == []


def test_builtin_extension_management_tools_enable_skills_and_plugins(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus on runtime extension work.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "description": "Focus skill",
                "tools": ["echo"],
                "prompt_fragments": ["prompts/focus.md"],
            }
        ),
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / "prompt.md").write_text("Use planner plugin guidance.", encoding="utf-8")
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "planner",
                "description": "Planning plugin",
                "tools": ["echo"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=SkillRegistry([]),
        session_state_store=store,
    )
    registry = ToolRegistry()
    registry.register("echo", "Echo", {}, lambda text="": text)
    register_builtin_tools(registry, context)
    runtime = AgentRuntime(
        model_client=SimpleNamespace(),
        tools=registry,
        protocol="scripted",
        model="test-model",
        enabled_tools=["skill.use", "skill.disable", "plugin.enable", "plugin.disable"],
    )
    AgentSession(runtime=runtime, system_prompt="Base prompt.", workspace=workspace, tool_context=context)
    context.enabled_tools = runtime.enabled_tools

    skill_enabled = asyncio.run(registry.execute("skill.use", {"name": "focus"}))
    tools_after_skill = runtime.enabled_tools
    state_after_skill = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    plugin_enabled = asyncio.run(registry.execute("plugin.enable", {"name": "planner"}))
    state_after_plugin = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    plugin_disabled = asyncio.run(registry.execute("plugin.disable", {"name": "planner"}))
    skill_disabled = asyncio.run(registry.execute("skill.disable", {"name": "focus"}))
    state_after_disable = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))

    assert skill_enabled.raw["added_tools"] == ["echo"]
    assert "Focus on runtime extension work." in context.session.system_prompt
    assert "Use planner plugin guidance." in context.session.system_prompt
    assert "echo" in tools_after_skill
    assert state_after_skill.enabled_skills == ["focus"]
    assert state_after_skill.skill_tools == {"focus": ["echo"]}
    assert plugin_enabled.raw["plugin"]["name"] == "planner"
    assert state_after_plugin.enabled_plugins == ["planner"]
    assert plugin_disabled.raw["removed_tools"] == []
    assert skill_disabled.raw["removed_tools"] == ["echo"]
    assert state_after_disable.enabled_skills == []
    assert state_after_disable.enabled_plugins == []
    assert "echo" not in runtime.enabled_tools

    impact = describe_tool_impact(ToolCall(id="call-skill", name="skill.use", arguments={"name": "focus"}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]


def test_builtin_agent_profile_tools_list_and_save_profiles(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryAgentProfileStore()
    spec = AgentSpec.from_overrides(
        protocol="openai-chat",
        model="gpt-test",
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["filesystem.read"],
        permission_profile="auto",
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
        agent_profile_store=store,
    )
    context.enabled_tools = ["filesystem.read", "agent.save_profile"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    runtime = AgentRuntime(
        model_client=SimpleNamespace(),
        tools=registry,
        protocol="openai-chat",
        model="gpt-test",
        enabled_tools=context.enabled_tools,
    )
    AgentSession(runtime=runtime, system_prompt="Profile prompt.", workspace=workspace, tool_context=context)

    saved = asyncio.run(registry.execute("agent.save_profile", {"agent_id": "reviewer", "name": "Reviewer"}))
    listed = asyncio.run(registry.execute("agent.profiles", {"query": "review"}))
    loaded = asyncio.run(store.load("tenant", "user", "reviewer"))

    assert saved.raw["profile"]["agent_id"] == "reviewer"
    assert listed.raw["profiles"][0]["name"] == "Reviewer"
    assert loaded.to_agent_spec().system_prompt == "Profile prompt."
    assert loaded.to_agent_spec().enabled_tools == ["filesystem.read", "agent.save_profile"]

    impact = describe_tool_impact(ToolCall(id="call-agent-profile", name="agent.save_profile", arguments={"agent_id": "reviewer"}))
    assert impact.risk == "medium"
    assert impact.operations == ["agent_profile_write"]


def test_builtin_team_tools_manage_session_local_members_and_messages(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    context.enabled_tools = ["filesystem.read"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "team.create",
            {
                "team_id": "feature",
                "name": "Feature Team",
                "members": [
                    {"agent_id": "researcher", "role": "research", "enabled_tools": ["filesystem.read"]},
                    {"agent_id": "reviewer", "role": "review"},
                ],
            },
        )
    )
    members = asyncio.run(registry.execute("team.members", {"team_id": "feature"}))
    sent = asyncio.run(
        registry.execute(
            "team.send",
            {"team_id": "feature", "from_agent": "lead", "to": "researcher", "message": "Check the repo."},
        )
    )
    inbox = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher", "mark_read": True}))
    inbox_after_read = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher"}))

    assert created.raw["team"]["team_id"] == "feature"
    assert members.raw["count"] == 2
    assert members.raw["members"][0]["agent_id"] == "researcher"
    assert sent.raw["count"] == 1
    assert inbox.raw["messages"][0]["message"] == "Check the repo."
    assert inbox_after_read.raw["messages"] == []

    impact = describe_tool_impact(ToolCall(id="call-team", name="team.send", arguments={"to": "researcher", "message": "Check the repo."}))
    assert impact.risk == "low"
    assert impact.operations == ["team_state_write"]
    assert "Check the repo" in impact.diff_preview


def test_src_origin_agent_team_and_send_message_aliases(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    team_store = InMemoryTeamStore()
    created_children = []

    class ChildSession:
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="agent result: %s" % prompt,
                messages=[Message.from_text("assistant", "agent result")],
            )

    async def create_child(spec, task_id=""):
        created_children.append(spec)
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        team_store=team_store,
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="lead",
            workspace_id="workspace",
            workspace_path=str(tmp_path),
        ),
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    team = asyncio.run(registry.execute("TeamCreate", {"team_name": "feature", "description": "Ship feature", "agent_type": "planner"}))
    sent = asyncio.run(registry.execute("SendMessage", {"to": "team-lead", "summary": "Repo check", "message": "Check the repo."}))
    inbox = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "team-lead"}))
    agent = asyncio.run(registry.execute("Agent", {"description": "Inspect repo", "prompt": "read files", "name": "researcher"}))
    deleted = asyncio.run(registry.execute("TeamDelete", {}))
    after_delete = asyncio.run(registry.execute("team.members", {"team_id": "feature"}))

    assert team.raw["team_name"] == "feature"
    assert team.raw["lead_agent_id"] == "team-lead"
    assert sent.raw["sent"][0]["to"] == "team-lead"
    assert inbox.raw["messages"][0]["message"] == "Check the repo."
    assert agent.raw["content"] == "agent result: read files"
    assert created_children[0].agent_id == "researcher"
    assert deleted.raw["deleted"] is True
    assert after_delete.is_error is True

    specs = {
        spec.name: spec.raw["metadata"]["alias_of"]
        for spec in registry.specs(["Agent", "Task", "SendMessage", "TeamCreate", "TeamDelete"])
    }
    assert specs == {
        "Agent": "agent.run",
        "Task": "agent.run",
        "SendMessage": "team.send",
        "TeamCreate": "team.create",
        "TeamDelete": "team.delete",
    }

    impact = describe_tool_impact(
        ToolCall(id="call-send", name="SendMessage", arguments={"to": "team-lead", "message": "Check the repo.", "team_name": "feature"})
    )
    assert impact.tool_name == "team.send"
    assert impact.operations == ["team_state_write"]
    assert impact.query == "feature"


def test_structured_output_tool_and_src_origin_alias(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        agent_spec=AgentSpec(metadata={
            "structured_output_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}, "score": {"type": "number"}},
                "required": ["answer"],
                "additionalProperties": False,
            }
        }),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    missing = asyncio.run(registry.execute("StructuredOutput", {"score": 0.9}))
    structured = asyncio.run(registry.execute("StructuredOutput", {"answer": "ok", "score": 0.9}))
    canonical = asyncio.run(registry.execute("structured.output", {"answer": "ok"}))

    assert missing.is_error is True
    assert "missing required argument: answer" in missing.content
    assert structured.content == "Structured output provided successfully"
    assert structured.raw["structured_output"] == {"answer": "ok", "score": 0.9}
    assert canonical.raw["structured_output"] == {"answer": "ok"}

    specs = {spec.name: spec for spec in registry.specs(["structured.output", "StructuredOutput"])}
    assert specs["StructuredOutput"].raw["metadata"]["alias_of"] == "structured.output"
    assert specs["StructuredOutput"].parameters["required"] == ["answer"]
    assert specs["structured.output"].raw["metadata"]["structured_output"] is True

    impact = describe_tool_impact(ToolCall(id="call-structured", name="StructuredOutput", arguments={"answer": "ok"}))
    assert impact.tool_name == "structured.output"
    assert impact.risk == "low"
    assert impact.operations == ["structured_output"]
    assert '"answer": "ok"' in impact.diff_preview


def test_src_origin_skill_alias_invokes_inline_skill(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "focus"
    skill_dir.mkdir(parents=True)
    (skill_dir / "prompt.md").write_text("Focus on {arguments}.", encoding="utf-8")
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "description": "Focus skill",
                "prompt_fragments": ["prompt.md"],
                "tools": ["filesystem.read"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        enabled_tools=["Skill", "skill.invoke", "filesystem.read"],
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    invoked = asyncio.run(registry.execute("Skill", {"skill": "/focus", "args": "agent core"}))

    assert invoked.is_error is False
    assert invoked.raw["success"] is True
    assert invoked.raw["commandName"] == "focus"
    assert invoked.raw["allowedTools"] == ["filesystem.read"]
    assert invoked.raw["status"] == "inline"
    assert invoked.raw["prompt"] == "Focus on agent core.\n\nArguments:\nagent core"
    assert "Continue using these instructions" in invoked.content

    specs = {spec.name: spec.raw["metadata"]["alias_of"] for spec in registry.specs(["Skill"])}
    assert specs == {"Skill": "skill.invoke"}

    impact = describe_tool_impact(ToolCall(id="call-skill", name="Skill", arguments={"skill": "focus", "args": "agent core"}))
    assert impact.tool_name == "skill.invoke"
    assert impact.risk == "high"
    assert impact.operations == ["skill_invoke"]
    assert impact.query == "focus"


def test_skill_invoke_forked_skill_uses_child_session_boundary(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "prompt.md").write_text("Research {arguments}.", encoding="utf-8")
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "research",
                "description": "Research skill",
                "prompt_fragments": ["prompt.md"],
                "tools": ["filesystem.read"],
                "metadata": {"context": "fork"},
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    created_children = []

    class ChildSession:
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="skill result: %s" % prompt,
                messages=[Message.from_text("assistant", "skill result")],
            )

    async def create_child(spec, task_id=""):
        created_children.append(spec)
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="lead",
            workspace_id="workspace",
            workspace_path=str(tmp_path),
            enabled_tools=["filesystem.read"],
        ),
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    invoked = asyncio.run(registry.execute("skill.invoke", {"skill": "research", "args": "repo"}))

    assert invoked.raw["success"] is True
    assert invoked.raw["status"] == "forked"
    assert invoked.raw["commandName"] == "research"
    assert invoked.raw["result"] == "skill result: Research repo.\n\nArguments:\nrepo"
    assert created_children[0].agent_id.startswith("skill_research_")
    assert created_children[0].metadata["skill"] == "research"
    assert created_children[0].enabled_tools == ["filesystem.read"]


def test_builtin_team_tools_use_shared_team_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    team_store = InMemoryTeamStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            team_store=team_store,
        )
        context.enabled_tools = ["filesystem.read"]
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        created = await first.execute(
            "team.create",
            {
                "team_id": "feature",
                "members": [{"agent_id": "researcher", "role": "research"}],
            },
        )
        members = await second.execute("team.members", {"team_id": "feature"})
        sent = await second.execute("team.send", {"team_id": "feature", "to": "researcher", "message": "Check the repo."})
        inbox = await first.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher", "mark_read": True})
        after_read = await second.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher"})
        return created, members, sent, inbox, after_read

    created, members, sent, inbox, after_read = asyncio.run(execute())

    assert created.raw["team"]["team_id"] == "feature"
    assert members.raw["members"][0]["agent_id"] == "researcher"
    assert sent.raw["count"] == 1
    assert inbox.raw["messages"][0]["message"] == "Check the repo."
    assert after_read.raw["messages"] == []


def test_builtin_team_run_member_delegates_and_delivers_result(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    created_children = []

    class ChildSession:
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="research result: %s" % prompt,
                messages=[Message.from_text("assistant", "research result")],
            )

    async def create_child(spec, task_id=""):
        created_children.append(spec)
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="lead",
            workspace_id="workspace",
            workspace_path=str(tmp_path),
        ),
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    asyncio.run(
        registry.execute(
            "team.create",
            {
                "team_id": "feature",
                "members": [
                    {
                        "agent_id": "researcher",
                        "role": "research",
                        "system_prompt": "Research carefully.",
                        "enabled_tools": ["filesystem.read"],
                    }
                ],
            },
        )
    )

    delegated = asyncio.run(
        registry.execute(
            "team.run_member",
            {"team_id": "feature", "agent_id": "researcher", "prompt": "inspect repo", "reply_to": "lead"},
        )
    )
    inbox = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "lead"}))

    assert delegated.raw["result"]["content"] == "research result: inspect repo"
    assert delegated.raw["delivered"]["type"] == "agent_result"
    assert inbox.raw["messages"][0]["message"] == "research result: inspect repo"
    assert created_children[0].agent_id == "researcher"
    assert created_children[0].system_prompt == "Research carefully."
    assert created_children[0].enabled_tools == ["filesystem.read"]

    impact = describe_tool_impact(ToolCall(id="call-team-run", name="team.run_member", arguments={"agent_id": "researcher", "prompt": "inspect repo"}))
    assert impact.risk == "high"
    assert impact.operations == ["team_state_write", "subagent"]


def test_builtin_command_tools_discover_and_render_workspace_commands(tmp_path: Path):
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text(
        "---\n"
        "description: Review a target path\n"
        "argument_hint: <path>\n"
        "aliases: inspect\n"
        "---\n"
        "Review this path carefully: {arguments}\n",
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    commands = asyncio.run(registry.execute("command.discover", {"query": "review"}))
    rendered = asyncio.run(registry.execute("command.render", {"name": "inspect", "arguments": "src"}))
    read = asyncio.run(registry.execute("command.read", {"name": "review"}))
    saved = asyncio.run(
        registry.execute(
            "command.save",
            {
                "name": "ship",
                "content": "Ship {arguments}",
                "description": "Ship target",
                "aliases": ["release"],
            },
        )
    )
    rendered_saved = asyncio.run(registry.execute("command.render", {"name": "release", "arguments": "v1"}))
    deleted = asyncio.run(registry.execute("command.delete", {"name": "ship"}))

    assert commands.raw["commands"][0]["name"] == "/review"
    assert commands.raw["commands"][0]["argumentHint"] == "<path>"
    assert commands.raw["commands"][0]["aliases"] == ["/inspect"]
    assert rendered.raw["prompt"] == "Review this path carefully: src"
    assert read.raw["content"] == "Review this path carefully: {arguments}\n"
    assert saved.raw["path"] == ".agents/commands/ship.md"
    assert rendered_saved.raw["prompt"] == "Ship v1"
    assert deleted.raw["deleted"] is True

    impact = describe_tool_impact(ToolCall(id="call-command", name="command.render", arguments={"name": "review"}))
    assert impact.operations == ["command_read"]
    save_impact = describe_tool_impact(ToolCall(id="call-command-save", name="command.save", arguments={"name": "ship", "content": "Ship {arguments}"}))
    assert save_impact.risk == "medium"
    assert save_impact.operations == ["command_write"]
    assert save_impact.paths == [".agents/commands/ship.md"]


def test_patch_apply_edits_and_creates_workspace_files(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("hello old world\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    unread = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )
    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {
                "edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}],
                "creates": [{"path": "created.txt", "content": "created\n"}],
            },
        )
    )

    assert unread.is_error is True
    assert "File has not been read yet" in unread.content
    assert read.is_error is False
    payload = result.raw
    assert result.is_error is False
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello new world\n"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert [item["path"] for item in payload["files"]] == ["notes.txt", "created.txt"]
    assert payload["editSummary"] == [
        {
            "filePath": "notes.txt",
            "oldString": "old",
            "newString": "new",
            "replaceAll": False,
            "occurrences": 1,
        }
    ]
    assert "--- a/notes.txt" in payload["diff"]


def test_patch_apply_exposes_file_edit_style_single_edit_metadata(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("hello old world\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["filePath"] == "notes.txt"
    assert result.raw["oldString"] == "old"
    assert result.raw["newString"] == "new"
    assert result.raw["replaceAll"] is False
    assert result.raw["originalFile"] == "hello old world\n"
    assert result.raw["structuredPatch"][0]["oldStart"] == 1
    assert result.raw["structuredPatch"][0]["newStart"] == 1
    assert result.raw["structuredPatch"][0]["lines"] == [
        "-hello old world",
        "+hello new world",
    ]
    assert result.raw["structuredPatches"][0]["filePath"] == "notes.txt"
    assert result.raw["structuredPatches"][0]["hunks"] == result.raw["structuredPatch"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink is not available on this platform")
def test_patch_apply_reports_symlink_target_for_followed_edits(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    target = tmp_path / "target.txt"
    link = tmp_path / "link.txt"
    target.write_text("hello old world\n", encoding="utf-8")
    link.symlink_to(target.name)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "link.txt"}))
    result = asyncio.run(
        registry.execute(
            "Edit",
            {"file_path": "link.txt", "old_string": "old", "new_string": "new"},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["filePath"] == "target.txt"
    assert result.raw["symlinkTarget"] == "target.txt"
    assert result.raw["files"][0]["symlinkTarget"] == "target.txt"
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == "hello new world\n"


def test_patch_apply_rejects_secret_replacement_in_team_memory(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    memory_path = tmp_path / ".agents" / "projects" / "project-key" / "memory" / "team" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("safe team note\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    fake_aws_key = "AKIA" + "A" * 16

    read = asyncio.run(
        registry.execute("filesystem.read", {"path": ".agents/projects/project-key/memory/team/MEMORY.md"})
    )
    result = asyncio.run(
        registry.execute(
            "Edit",
            {
                "file_path": ".agents/projects/project-key/memory/team/MEMORY.md",
                "old_string": "safe team note",
                "new_string": "aws=%s" % fake_aws_key,
            },
        )
    )

    assert read.is_error is False
    assert result.is_error is True
    assert "Content contains potential secrets (AWS Access Token)" in result.content
    assert memory_path.read_text(encoding="utf-8") == "safe team note\n"


def test_patch_apply_exposes_src_origin_git_diff_for_single_file_edit(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "agent@example.com")
    _run_git(repo, "config", "user.name", "Agent Test")
    _run_git(repo, "remote", "add", "origin", "ssh://git@github.com/example/agents-test.git")
    (repo / "tracked.py").write_text("value = 'old'\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.py")
    _run_git(repo, "commit", "-m", "initial")
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "tracked.py"}))
    result = asyncio.run(
        registry.execute(
            "Edit",
            {"file_path": "tracked.py", "old_string": "old", "new_string": "new"},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["gitDiff"]["filename"] == "tracked.py"
    assert result.raw["gitDiff"]["status"] == "modified"
    assert result.raw["gitDiff"]["additions"] == 1
    assert result.raw["gitDiff"]["deletions"] == 1
    assert result.raw["gitDiff"]["changes"] == 2
    assert result.raw["gitDiff"]["repository"] == "example/agents-test"
    assert "-value = 'old'" in result.raw["gitDiff"]["patch"]
    assert "+value = 'new'" in result.raw["gitDiff"]["patch"]


def test_patch_apply_rejects_noop_and_ambiguous_edits(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("old old\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    noop = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "old"}]},
        )
    )
    ambiguous = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )
    all_matches = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new", "replace_all": True}]},
        )
    )

    assert read.is_error is False
    assert noop.is_error is True
    assert "old_text and new_text are exactly the same" in noop.content
    assert ambiguous.is_error is True
    assert "Found 2 matches" in ambiguous.content
    assert "replace_all is false" in ambiguous.content
    assert all_matches.is_error is False
    assert all_matches.raw["editSummary"][0]["replaceAll"] is True
    assert all_matches.raw["editSummary"][0]["occurrences"] == 2
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "new new\n"


def test_patch_apply_matches_and_preserves_curly_quote_style(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("title = \u201cOld name\u201d\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": '"Old name"', "new_text": '"New name"'}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["oldString"] == "\u201cOld name\u201d"
    assert result.raw["newString"] == '"New name"'
    assert result.raw["editSummary"][0]["oldString"] == "\u201cOld name\u201d"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "title = \u201cNew name\u201d\n"


def test_patch_apply_desanitizes_file_edit_placeholders(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "transcript.xml").write_text(
        "<function_results><result>old</result></function_results>\n",
        encoding="utf-8",
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "transcript.xml"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {
                "edits": [
                        {
                            "path": "transcript.xml",
                            "old_text": "<fnr><r>old</r></function_results>",
                            "new_text": "<fnr><r>new</r></function_results>",
                        }
                ]
            },
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["oldString"] == "<function_results><result>old</result></function_results>"
    assert result.raw["newString"] == "<function_results><result>new</result></function_results>"
    assert result.raw["editSummary"][0]["newString"] == "<function_results><result>new</result></function_results>"
    assert (
        tmp_path / "transcript.xml"
    ).read_text(encoding="utf-8") == "<function_results><result>new</result></function_results>\n"


def test_patch_apply_strips_trailing_whitespace_from_non_markdown_new_text(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("alpha\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "alpha", "new_text": "beta   \nnext\t  "}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["newString"] == "beta\nnext"
    assert result.raw["editSummary"][0]["newString"] == "beta\nnext"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "beta\nnext\n"


def test_patch_apply_preserves_markdown_trailing_whitespace_in_new_text(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "guide.md").write_text("alpha\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "guide.md"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "guide.md", "old_text": "alpha", "new_text": "beta  \nnext\t  "}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["newString"] == "beta  \nnext\t  "
    assert (tmp_path / "guide.md").read_text(encoding="utf-8") == "beta  \nnext\t  \n"


def test_patch_apply_rejects_later_edit_that_targets_previous_new_text(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("one\ntwo\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {
                "edits": [
                    {"path": "notes.txt", "old_text": "one", "new_text": "one beta"},
                    {"path": "notes.txt", "old_text": "beta\n", "new_text": "gamma\n"},
                ]
            },
        )
    )

    assert read.is_error is False
    assert result.is_error is True
    assert "old_text is a substring of a new_text from a previous edit" in result.content
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "one\ntwo\n"


def test_patch_apply_empty_replacement_removes_trailing_newline_like_file_edit(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("keep\nremove me\nnext\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "remove me", "new_text": ""}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert result.raw["editSummary"][0]["occurrences"] == 1
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep\nnext\n"


def test_patch_apply_preserves_crlf_for_existing_file_edit(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_bytes(b"old\r\ntext\r\n")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert (tmp_path / "notes.txt").read_bytes() == b"new\r\ntext\r\n"


def test_patch_apply_preserves_utf16le_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("hello old world\n", encoding="utf-16")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )

    assert read.is_error is False
    assert result.is_error is False
    assert (tmp_path / "notes.txt").read_bytes().startswith(b"\xff\xfe")
    assert (tmp_path / "notes.txt").read_text(encoding="utf-16") == "hello new world\n"


def test_patch_apply_preserves_utf16_without_bom_for_existing_file(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_bytes("hello old world\n".encode("utf-16le"))
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "notes.txt"}))
    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}]},
        )
    )
    payload = (tmp_path / "notes.txt").read_bytes()

    assert read.is_error is False
    assert result.is_error is False
    assert not payload.startswith(b"\xff\xfe")
    assert payload.decode("utf-16le") == "hello new world\n"


def test_filesystem_move_and_delete_are_native_workspace_tools(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "old.txt").write_text("move me", encoding="utf-8")
    (tmp_path / "trash").mkdir()
    (tmp_path / "trash" / "note.txt").write_text("delete me", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    moved = asyncio.run(
        registry.execute(
            "filesystem.move",
            {"source_path": "old.txt", "destination_path": "renamed/new.txt"},
        )
    )
    deleted = asyncio.run(registry.execute("filesystem.delete", {"path": "trash", "recursive": True}))

    assert moved.is_error is False
    assert moved.raw["destination_path"] == "renamed/new.txt"
    assert (tmp_path / "renamed" / "new.txt").read_text(encoding="utf-8") == "move me"
    assert not (tmp_path / "old.txt").exists()
    assert deleted.raw["deleted"] is True
    assert not (tmp_path / "trash").exists()


def test_tool_impact_describes_patch_paths_and_preview():
    call = ToolCall(
        id="call-1",
        name="patch.apply",
        arguments={"edits": [{"path": "app.py", "old_text": "a = 1", "new_text": "a = 2"}]},
    )

    impact = describe_tool_impact(call).to_dict()

    assert impact["risk"] == "medium"
    assert impact["writes_files"] is True
    assert impact["paths"] == ["app.py"]
    assert "a = 2" in impact["diff_preview"]


def test_tool_impact_describes_file_move_and_git_commit():
    move = describe_tool_impact(
        ToolCall(
            id="call-1",
            name="filesystem.move",
            arguments={"source_path": "old.py", "destination_path": "new.py"},
        )
    ).to_dict()
    commit = describe_tool_impact(
        ToolCall(
            id="call-2",
            name="git.commit",
            arguments={"message": "ship", "all": True},
        )
    ).to_dict()

    assert move["risk"] == "medium"
    assert move["writes_files"] is True
    assert move["paths"] == ["old.py", "new.py"]
    assert commit["risk"] == "high"
    assert commit["writes_files"] is True
    assert commit["commands"] == ["git commit -a"]


def test_git_native_tools_stage_commit_log_and_show(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allowed_commands=("git",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(context.sandbox_client.run_command("git init"))
    asyncio.run(context.sandbox_client.run_command("git config user.email test@example.com"))
    asyncio.run(context.sandbox_client.run_command("git config user.name Test"))
    added = asyncio.run(registry.execute("git.add", {"paths": ["app.py"]}))
    committed = asyncio.run(registry.execute("git.commit", {"message": "initial commit"}))
    log = asyncio.run(registry.execute("git.log", {"max_count": 1}))
    shown = asyncio.run(registry.execute("git.show", {"revision": "HEAD", "patch": False}))

    assert added.is_error is False
    assert committed.is_error is False
    assert "initial commit" in log.raw["stdout"]
    assert "initial commit" in shown.raw["stdout"]


def test_test_discover_suggests_workspace_test_commands(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("test.discover", {}))

    assert result.is_error is False
    assert result.raw["recommended_command"] == "pytest"
    assert result.raw["commands"][0]["confidence"] == "high"


class FakeBrowserSandbox:
    async def run_command(self, command, timeout_seconds=30.0):
        return SandboxCommandResult(
            command=command,
            exit_code=0,
            stdout=json.dumps(
                {
                    "url": "https://example.com",
                    "path": "downloads/page.html",
                    "status": 200,
                    "content_type": "text/html",
                    "bytes": 12,
                    "truncated": False,
                }
            ),
        )


def test_browser_open_uses_sandbox_network_and_process_path():
    policy = SandboxPolicy.for_workspace(
        Path("."),
        allow_file_write=True,
        allow_process=True,
        allow_network=True,
        allowed_commands=("python3",),
    )
    context = SimpleNamespace(sandbox=policy, sandbox_client=FakeBrowserSandbox())

    result = asyncio.run(browser_open(context, "https://example.com", output_path="downloads/page.html"))

    assert result["status"] == 200
    assert result["path"] == "downloads/page.html"


class RecordingBrowserSandbox:
    def __init__(self, workspace: WorkspaceContext, output_path: str):
        self.workspace = workspace
        self.output_path = output_path

    async def run_command(self, command, timeout_seconds=30.0):
        target = self.workspace.path / self.output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<html>ok</html>", encoding="utf-8")
        return SandboxCommandResult(
            command=command,
            exit_code=0,
            stdout=json.dumps(
                {
                    "url": "https://example.com",
                    "path": self.output_path,
                    "status": 200,
                    "content_type": "text/html",
                    "bytes": 15,
                    "truncated": False,
                }
            ),
        )


def test_browser_open_records_run_artifact(tmp_path: Path):
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=workspace_path,
    )
    artifact_store = InMemoryArtifactStore()
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allow_network=True,
        allowed_commands=("python3",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=RecordingBrowserSandbox(
            workspace,
            (tmp_path / "blob" / "runs" / "run-1" / "artifacts" / "downloads" / "browser-open.html").as_posix(),
        ),
        artifact_store=artifact_store,
        artifact_blob_store=LocalArtifactBlobStore(tmp_path / "blob", include_workspace_scope=False),
    )
    context.current_run_id = "run-1"
    context.current_tool_call_id = "call-1"

    result = asyncio.run(browser_open(context, "https://example.com"))
    artifacts = asyncio.run(artifact_store.list_for_run("run-1"))

    assert result["artifact"]["role"] == "tool_artifact"
    assert artifacts[0].tool_call_id == "call-1"
    assert artifacts[0].workspace_path == ""
    assert artifacts[0].uri.endswith("/blob/runs/run-1/artifacts/downloads/browser-open.html")
    assert artifacts[0].sha256


def test_skill_registry_loads_prompt_fragments_and_tool_names(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus on {topic}.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "version": "1.0.0",
                "paths": ["src/**/*.py"],
                "prompt_fragments": ["prompts/focus.md"],
                "tools": ["echo"],
            }
        ),
        encoding="utf-8",
    )

    registry = SkillRegistry.load(SkillLoader(tmp_path), ["focus"], context={"topic": "agents"})

    assert registry.names() == ["focus"]
    assert registry.prompt_text() == "Focus on agents."
    assert registry.tool_names() == ["echo"]
    assert registry.skills[0].path_patterns == ["src/**/*.py"]
    assert registry.skills[0].metadata["paths"] == ["src/**/*.py"]
