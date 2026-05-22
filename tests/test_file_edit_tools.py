import asyncio
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import (
    ToolRegistry,
    ToolRuntimeContext,
    register_builtin_tools,
)
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
