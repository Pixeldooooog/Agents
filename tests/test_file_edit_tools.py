import asyncio
import json
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import (
    ToolRegistry,
    ToolRuntimeContext,
    register_builtin_tools,
)
from agents.kernel.capabilities.tools.builtin import patch as patch_tools
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy


def _registry(tmp_path: Path) -> ToolRegistry:
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
    return registry


def test_src_origin_edit_empty_old_string_creates_file_without_prior_read(tmp_path: Path):
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {"file_path": "created.txt", "old_string": "", "new_string": "created\n"},
        )
    )

    assert result.is_error is False
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert result.raw["filePath"] == "created.txt"
    assert result.raw["oldString"] == ""
    assert result.raw["newString"] == "created\n"
    assert result.raw["originalFile"] == ""
    assert result.raw["userModified"] is False
    assert result.raw["structuredPatch"][0]["lines"] == ["+created"]


def test_src_origin_edit_empty_old_string_rejects_existing_nonempty_file(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("existing\n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {"file_path": "notes.txt", "old_string": "", "new_string": "created\n"},
        )
    )

    assert result.is_error is True
    assert result.content == "Cannot create new file - file already exists."
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "existing\n"


def test_src_origin_edit_empty_old_string_replaces_blank_file(tmp_path: Path):
    (tmp_path / "blank.txt").write_text("  \n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {"file_path": "blank.txt", "old_string": "", "new_string": "created\n"},
        )
    )

    assert result.is_error is False
    assert (tmp_path / "blank.txt").read_text(encoding="utf-8") == "created\n"
    assert result.raw["files"][0]["action"] == "overwrite"
    assert result.raw["originalFile"] == "  \n"


def test_src_origin_edit_rejects_notebooks_before_prior_read(tmp_path: Path):
    notebook = {
        "cells": [{"cell_type": "markdown", "source": "old\n", "metadata": {}}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {
                "file_path": "analysis.ipynb",
                "old_string": "old",
                "new_string": "new",
            },
        )
    )

    assert result.is_error is True
    assert result.content == "File is a Jupyter Notebook. Use the NotebookEdit tool to edit this file."


def test_src_origin_edit_missing_file_reports_cwd_and_similar_file(tmp_path: Path):
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {
                "file_path": "README.txt",
                "old_string": "old",
                "new_string": "new",
            },
        )
    )

    assert result.is_error is True
    assert "File does not exist" in result.content
    assert "Note: your current working directory is %s" % tmp_path in result.content
    assert "Did you mean README.md?" in result.content


def test_src_origin_edit_rejects_noop_before_prior_read(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("old\n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {
                "file_path": "notes.txt",
                "old_string": "old",
                "new_string": "old",
            },
        )
    )

    assert result.is_error is True
    assert result.content == "No changes to make: old_string and new_string are exactly the same."
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "old\n"


def test_src_origin_edit_rejects_oversized_file_before_read(tmp_path: Path, monkeypatch):
    (tmp_path / "large.txt").write_text("123456789", encoding="utf-8")
    monkeypatch.setattr(patch_tools, "SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES", 8)
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "Edit",
            {
                "file_path": "large.txt",
                "old_string": "123",
                "new_string": "abc",
            },
        )
    )

    assert result.is_error is True
    assert result.content == "File is too large to edit (9 B). Maximum editable file size is 8 B."
    assert (tmp_path / "large.txt").read_text(encoding="utf-8") == "123456789"


def test_patch_apply_keeps_empty_old_text_rejected(tmp_path: Path):
    registry = _registry(tmp_path)

    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {"edits": [{"path": "created.txt", "old_text": "", "new_text": "created\n"}]},
        )
    )

    assert result.is_error is True
    assert result.content == "old_text is required"
