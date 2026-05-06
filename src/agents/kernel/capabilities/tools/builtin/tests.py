from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


TEST_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Test command to run in the workspace."},
        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 600},
    },
}

TEST_DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative path to inspect."},
    },
}


async def run_tests(
    context: ToolRuntimeContext,
    command: str = "pytest",
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    result = await context.sandbox_client.run_command(command or "pytest", timeout_seconds=timeout_seconds)
    return result.to_dict()


def discover_tests(context: ToolRuntimeContext, path: str = ".") -> dict[str, Any]:
    decision = context.sandbox.authorize_file_read(path or ".")
    if not decision.allowed:
        raise PermissionError(decision.reason)
    root = context.sandbox.resolve_workspace_path(path or ".")
    if root.is_file():
        root = root.parent
    candidates = _discover_candidates(root)
    return {
        "path": context.sandbox.relative_workspace_path(root),
        "commands": candidates,
        "recommended_command": candidates[0]["command"] if candidates else "",
    }


def _discover_candidates(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(command: str, reason: str, confidence: str = "medium") -> None:
        if command not in seen:
            seen.add(command)
            candidates.append({"command": command, "reason": reason, "confidence": confidence})

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        scripts = payload.get("scripts") if isinstance(payload, dict) else {}
        if isinstance(scripts, dict) and scripts.get("test"):
            package_manager = str(payload.get("packageManager") or "")
            if package_manager.startswith("bun") or (root / "bun.lockb").exists() or (root / "bun.lock").exists():
                add("bun test", "package.json test script with Bun project markers", "high")
            elif (root / "pnpm-lock.yaml").exists():
                add("pnpm test", "package.json test script with pnpm-lock.yaml", "high")
            elif (root / "yarn.lock").exists():
                add("yarn test", "package.json test script with yarn.lock", "high")
            else:
                add("npm test", "package.json test script", "high")

    if any((root / name).is_file() for name in ("pytest.ini", "setup.cfg", "tox.ini")):
        add("pytest", "Python test configuration file found", "high")
    if (root / "pyproject.toml").is_file():
        text = _read_text(root / "pyproject.toml")
        if "[tool.pytest" in text or (root / "tests").is_dir():
            add("pytest", "pyproject.toml and Python tests found", "high")
    if (root / "tests").is_dir() and any(root.glob("**/test_*.py")):
        add("pytest", "tests/ contains pytest-style files", "medium")

    makefile = _first_existing(root, ("makefile", "Makefile"))
    if makefile is not None:
        text = _read_text(makefile)
        targets = set(re.findall(r"^([A-Za-z0-9_.-]+):", text, flags=re.MULTILINE))
        if "test" in targets:
            add("make test", "%s has a test target" % makefile.name, "high")
        if "check" in targets:
            add("make check", "%s has a check target" % makefile.name, "medium")

    if (root / "Cargo.toml").is_file():
        add("cargo test", "Cargo.toml found", "high")
    if (root / "go.mod").is_file():
        add("go test ./...", "go.mod found", "high")

    return candidates


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
