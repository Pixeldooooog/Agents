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
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    return registry


def test_grep_missing_path_reports_src_origin_style_error(tmp_path: Path):
    (tmp_path / "README.md").write_text("needle\n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "README.txt"}))
    alias_result = asyncio.run(registry.execute("Grep", {"pattern": "needle", "path": "missing"}))

    assert result.is_error is True
    assert "Path does not exist: README.txt" in result.content
    assert "Note: your current working directory is %s" % tmp_path in result.content
    assert "Did you mean README.md?" in result.content
    assert result.raw["reason"] == "path_not_found"
    assert alias_result.is_error is True
    assert "Path does not exist: missing" in alias_result.content


def test_glob_validates_search_directory(tmp_path: Path):
    (tmp_path / "src.py").write_text("needle\n", encoding="utf-8")
    registry = _registry(tmp_path)

    missing = asyncio.run(registry.execute("search.glob", {"pattern": "*.py", "path": "missing"}))
    file_path = asyncio.run(registry.execute("Glob", {"pattern": "*.py", "path": "src.py"}))

    assert missing.is_error is True
    assert "Directory does not exist: missing" in missing.content
    assert missing.raw["reason"] == "path_not_found"
    assert file_path.is_error is True
    assert file_path.content == "Path is not a directory: src.py"
    assert file_path.raw["reason"] == "path_not_directory"


def test_grep_skips_src_origin_vcs_directories(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / ".hg").mkdir()
    (tmp_path / "src" / "app.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / ".hg" / "store.txt").write_text("needle\n", encoding="utf-8")
    registry = _registry(tmp_path)

    result = asyncio.run(registry.execute("search.grep", {"pattern": "needle", "path": "."}))

    assert result.is_error is False
    assert result.content == "Found 1 file\nsrc/app.py"
    assert result.raw["filenames"] == ["src/app.py"]
    assert all(not match["path"].startswith(".hg/") for match in result.raw["matches"])
