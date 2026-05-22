import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy


def _context_and_registry(root: Path) -> tuple[ToolRuntimeContext, ToolRegistry]:
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
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    return context, registry


def _write_nested_skill(root: Path, relative_parent: str, name: str, prompt: str) -> Path:
    skill_root = root / relative_parent / ".claude" / "skills"
    skill_dir = skill_root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": name,
                "description": "Dynamically discovered skill",
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    return skill_root


def test_filesystem_read_discovers_nested_skill_dirs_and_skill_invocation(tmp_path: Path):
    (tmp_path / "src" / "feature").mkdir(parents=True)
    (tmp_path / "src" / "feature" / "notes.txt").write_text("notes\n", encoding="utf-8")
    skill_root = _write_nested_skill(tmp_path, "src/feature", "focus", "Focus on {arguments}.")
    context, registry = _context_and_registry(tmp_path)

    read = asyncio.run(registry.execute("filesystem.read", {"path": "src/feature/notes.txt"}))
    invoked = asyncio.run(registry.execute("Skill", {"skill": "focus", "args": "agent core"}))

    assert read.is_error is False
    assert context.dynamic_skill_dir_triggers == {str(skill_root)}
    assert context.dynamic_skill_dirs == {str(skill_root)}
    assert context.skill_registry.names() == ["focus"]
    assert invoked.is_error is False
    assert invoked.raw["prompt"].startswith("Focus on agent core.")
    assert "Arguments:\nagent core" in invoked.raw["prompt"]


def test_filesystem_write_discovers_nested_skill_dirs(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    skill_root = _write_nested_skill(tmp_path, "pkg", "writer", "Write {arguments}.")
    context, registry = _context_and_registry(tmp_path)

    written = asyncio.run(registry.execute("filesystem.write", {"path": "pkg/generated.txt", "content": "ok\n"}))

    assert written.is_error is False
    assert context.dynamic_skill_dir_triggers == {str(skill_root)}
    assert context.skill_registry.names() == ["writer"]


def test_patch_apply_create_discovers_nested_skill_dirs(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    skill_root = _write_nested_skill(tmp_path, "pkg", "editor", "Edit {arguments}.")
    context, registry = _context_and_registry(tmp_path)

    patched = asyncio.run(
        registry.execute(
            "patch.apply",
            {
                "creates": [
                    {
                        "path": "pkg/generated.txt",
                        "content": "ok\n",
                    }
                ]
            },
        )
    )

    assert patched.is_error is False
    assert context.dynamic_skill_dir_triggers == {str(skill_root)}
    assert context.skill_registry.names() == ["editor"]


def test_filesystem_read_skips_gitignored_nested_skill_dirs(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is unavailable")

    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "notes.txt").write_text("notes\n", encoding="utf-8")
    skill_root = _write_nested_skill(
        tmp_path,
        "ignored",
        "ignored-helper",
        "Ignore {arguments}.",
    )
    context, registry = _context_and_registry(tmp_path)

    read = asyncio.run(
        registry.execute("filesystem.read", {"path": "ignored/notes.txt"})
    )
    invoked = asyncio.run(
        registry.execute("Skill", {"skill": "ignored-helper", "args": "agent core"})
    )

    assert read.is_error is False
    assert context.dynamic_skill_dir_triggers == set()
    assert context.dynamic_skill_dirs == set()
    assert str(skill_root) in context.dynamic_skill_dirs_checked
    assert getattr(context, "skill_registry", None) is None
    assert invoked.is_error is True
