from __future__ import annotations

import asyncio
import os
import shlex
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.runtime import AgentRuntime, ScriptedModelClient, StaticToolPermissionPolicy
from agents.kernel.schema import Message, ModelResponse, ToolCall


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    detail: str


def run_smoke() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    with tempfile.TemporaryDirectory(prefix="agents-smoke-") as raw_root:
        root = Path(raw_root)
        checks.append(_server_health_check(root / "server.db"))
        checks.extend(asyncio.run(_workspace_runtime_check(root / "workspace")))
    return checks


def main() -> int:
    try:
        checks = run_smoke()
    except Exception as exc:  # noqa: BLE001 - this is the human-facing smoke boundary.
        print("smoke failed: %s" % exc, file=sys.stderr)
        return 1

    for check in checks:
        print("ok  %-18s %s" % (check.name, check.detail))
    print("smoke passed: %d checks" % len(checks))
    return 0


def _server_health_check(db_path: Path) -> SmokeCheck:
    old_db_path = os.environ.get("AGENT_DB_PATH")
    os.environ["AGENT_DB_PATH"] = str(db_path)
    try:
        from agents.interfaces.server.app import create_app
        from agents.interfaces.server.core.logging import logger

        previous_disabled = logger.disabled
        logger.disabled = True
        try:
            response = TestClient(create_app()).get("/health")
        finally:
            logger.disabled = previous_disabled
    finally:
        if old_db_path is None:
            os.environ.pop("AGENT_DB_PATH", None)
        else:
            os.environ["AGENT_DB_PATH"] = old_db_path
    if response.status_code != 200:
        raise RuntimeError("server health returned HTTP %s" % response.status_code)
    payload = response.json()
    status = ((payload.get("data") or {}).get("status") if isinstance(payload, dict) else "") or ""
    if status != "ok":
        raise RuntimeError("server health returned unexpected payload: %s" % payload)
    return SmokeCheck("server", "health endpoint ok")


async def _workspace_runtime_check(workspace_path: Path) -> list[SmokeCheck]:
    workspace_path.mkdir(parents=True, exist_ok=True)
    registry, context = _tool_registry(workspace_path)
    checks: list[SmokeCheck] = []

    await _must_tool(registry, "filesystem.write", {"path": "demo.py", "content": "def meaning():\n    return 42\n"})
    await _must_tool(
        registry,
        "filesystem.write",
        {
            "path": "tests/test_demo.py",
            "content": "from demo import meaning\n\n\ndef test_meaning():\n    assert meaning() == 42\n",
        },
    )
    listed = await _must_tool(registry, "filesystem.list", {"path": "."})
    entries = {entry["name"] for entry in listed.raw["entries"]}
    if not {"demo.py", "tests"}.issubset(entries):
        raise RuntimeError("filesystem.list did not include expected files")
    checks.append(SmokeCheck("filesystem", "read/list/write ok"))

    grep = await _must_tool(registry, "search.grep", {"pattern": "meaning", "path": "."})
    if not grep.raw["matches"]:
        raise RuntimeError("search.grep did not find expected match")
    checks.append(SmokeCheck("search", "workspace grep ok"))

    await _must_tool(registry, "filesystem.move", {"source_path": "demo.py", "destination_path": "src/demo.py"})
    await _must_tool(registry, "filesystem.write", {"path": "demo.py", "content": "from src.demo import meaning\n"})
    discovered = await _must_tool(registry, "test.discover", {"path": "."})
    if not discovered.raw["recommended_command"]:
        raise RuntimeError("test.discover did not recommend a command")
    command = "%s -c %s" % (
        shlex.quote(sys.executable),
        shlex.quote("from src.demo import meaning; assert meaning() == 42"),
    )
    test_run = await _must_tool(registry, "test.run", {"command": command, "timeout_seconds": 30})
    if test_run.raw["exit_code"] != 0:
        raise RuntimeError("test.run failed: %s" % test_run.raw)
    checks.append(SmokeCheck("test", "discover/run ok"))

    await context.sandbox_client.run_command("git init")
    await context.sandbox_client.run_command("git config user.email smoke@example.com")
    await context.sandbox_client.run_command("git config user.name Agents Smoke")
    await _must_tool(registry, "git.add", {"all": True})
    committed = await _must_tool(registry, "git.commit", {"message": "smoke commit"})
    if committed.raw["exit_code"] != 0:
        raise RuntimeError("git.commit failed: %s" % committed.raw)
    log = await _must_tool(registry, "git.log", {"max_count": 1})
    shown = await _must_tool(registry, "git.show", {"revision": "HEAD", "patch": False})
    if "smoke commit" not in log.raw["stdout"] or "smoke commit" not in shown.raw["stdout"]:
        raise RuntimeError("git log/show did not include smoke commit")
    checks.append(SmokeCheck("git", "add/commit/log/show ok"))

    await _runtime_tool_loop(registry, workspace_path)
    checks.append(SmokeCheck("runtime", "scripted model tool loop ok"))

    await _must_tool(registry, "filesystem.delete", {"path": "runtime.txt"})
    if (workspace_path / "runtime.txt").exists():
        raise RuntimeError("filesystem.delete did not remove runtime.txt")
    checks.append(SmokeCheck("cleanup", "delete ok"))
    return checks


def _tool_registry(workspace_path: Path) -> tuple[ToolRegistry, ToolRuntimeContext]:
    workspace = WorkspaceContext(
        tenant_id="smoke",
        user_id="local",
        agent_id="smoke-agent",
        workspace_id="default",
        root=workspace_path,
        path=workspace_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allowed_commands=("git", Path(sys.executable).name),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    return registry, context


async def _runtime_tool_loop(registry: ToolRegistry, workspace_path: Path) -> None:
    call = ToolCall(
        id="call-write",
        name="filesystem.write",
        arguments={"path": "runtime.txt", "content": "created by runtime\n"},
    )
    model = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call]), stop_reason="tool_calls"),
            ModelResponse(message=Message.from_text("assistant", "runtime ok")),
        ]
    )
    runtime = AgentRuntime(
        model_client=model,
        tools=registry,
        protocol="scripted",
        model="scripted-smoke",
        permission_policy=StaticToolPermissionPolicy(),
    )
    result = await runtime.run([Message.from_text("user", "write a runtime file")], run_id="smoke-run")
    if result.status != "finished" or result.content != "runtime ok":
        raise RuntimeError("runtime returned unexpected result: %s" % result)
    if (workspace_path / "runtime.txt").read_text(encoding="utf-8") != "created by runtime\n":
        raise RuntimeError("runtime tool loop did not write expected file")


async def _must_tool(registry: ToolRegistry, name: str, arguments: dict):
    result = await registry.execute(name, arguments, run_id="smoke-run")
    if result.is_error:
        raise RuntimeError("%s failed: %s" % (name, result.content))
    return result

