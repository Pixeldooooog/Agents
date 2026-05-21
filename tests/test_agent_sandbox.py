import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agents.kernel.capabilities.sandbox import (
    DockerSandboxProvider,
    InMemorySandboxStore,
    LocalSandboxProvider,
    SQLiteSandboxStore,
    SandboxEventRecord,
    SandboxLeaseRecord,
    SandboxWorkspaceSnapshotRecord,
    SandboxProfile,
    WorkspaceSnapshot,
    sandbox_policy_from_settings,
    sandbox_profile_from_settings,
)
from agents.kernel.capabilities.sandbox.recording import SandboxToolExecutionRecorder
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools
from agents.kernel.schema import ToolCall
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.persistence import SQLiteDatabase
from agents.kernel.state import ArtifactRecord, SQLiteArtifactStore


def _workspace(tmp_path: Path) -> WorkspaceContext:
    path = tmp_path / "tenant" / "user" / "agent" / "workspace"
    path.mkdir(parents=True)
    return WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=path,
    )


def test_local_sandbox_client_keeps_data_in_workspace(tmp_path):
    workspace = _workspace(tmp_path)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    client = LocalSandboxProvider().acquire(workspace, policy)

    written = client.write_text("notes/todo.txt", "ship sandbox tools")
    read = client.read_text("notes/todo.txt")
    listed = client.list_dir("notes")

    assert written.path == "notes/todo.txt"
    assert read.content == "ship sandbox tools"
    assert listed.entries[0].path == "notes/todo.txt"
    assert (workspace.path / "notes" / "todo.txt").read_text(encoding="utf-8") == "ship sandbox tools"


def test_local_sandbox_background_command_streams_to_workspace_file(tmp_path):
    workspace = _workspace(tmp_path)
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    client = LocalSandboxProvider().acquire(workspace, policy)

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
        handle = await client.start_background_command(
            "shell_test",
            "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
            ".agents/task-output/shell_test.log",
            timeout_seconds=5.0,
        )
        await asyncio.wait_for(handle._task, timeout=2.0)
        return handle, client.read_text(handle.output_path)

    handle, output = asyncio.run(execute())

    assert handle.status == "completed"
    assert handle.exit_code == 0
    assert output.path == ".agents/task-output/shell_test.log"
    assert output.content == "start\ndone\n"


def test_local_sandbox_text_read_rejects_binary_files(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    with pytest.raises(ValueError, match="binary"):
        client.read_text("image.png")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is not available on this platform")
def test_local_sandbox_rejects_special_file_read_and_write_targets(tmp_path):
    workspace = _workspace(tmp_path)
    fifo_path = workspace.path / "pipe"
    os.mkfifo(fifo_path)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    client = LocalSandboxProvider().acquire(workspace, policy)

    with pytest.raises(ValueError, match="special file \\(fifo\\): pipe"):
        client.read_text("pipe")
    with pytest.raises(ValueError, match="special file \\(fifo\\): pipe"):
        client.write_text("pipe", "data")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is not available on this platform")
def test_local_sandbox_rejects_special_background_output_targets(tmp_path):
    workspace = _workspace(tmp_path)
    output_path = workspace.path / ".agents" / "task-output" / "shell_test.log"
    output_path.parent.mkdir(parents=True)
    os.mkfifo(output_path)
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    client = LocalSandboxProvider().acquire(workspace, policy)

    async def execute():
        with pytest.raises(ValueError, match=r"special file \(fifo\): \.agents/task-output/shell_test\.log"):
            await client.start_background_command(
                "shell_test",
                "%s -c %s" % (shlex.quote(sys.executable), shlex.quote("print('ok')")),
                ".agents/task-output/shell_test.log",
                timeout_seconds=5.0,
            )

    asyncio.run(execute())


def test_local_sandbox_read_text_supports_line_ranges(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "notes.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    result = client.read_text("notes.txt", offset=2, limit=2)

    assert result.content == "two\nthree\n"
    assert result.start_line == 2
    assert result.num_lines == 2
    assert result.total_lines == 4
    assert result.is_partial_view is True


def test_local_sandbox_grep_skips_binary_files(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "note.txt").write_text("needle\n", encoding="utf-8")
    (workspace.path / "payload.bin").write_bytes(b"needle\x00binary")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    result = client.grep("needle")

    assert [match.path for match in result.matches] == ["note.txt"]


def test_local_sandbox_grep_filters_files_with_glob_patterns(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "src").mkdir()
    (workspace.path / "src" / "app.py").write_text("needle\n", encoding="utf-8")
    (workspace.path / "src" / "view.tsx").write_text("needle\n", encoding="utf-8")
    (workspace.path / "src" / "readme.md").write_text("needle\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    brace = client.grep("needle", path="src", glob_pattern="*.{py,tsx}")
    comma = client.grep("needle", path="src", glob_pattern="*.py,*.md")
    exclude = client.grep("needle", path="src", glob_pattern="*.{py,tsx} !*.tsx")

    assert sorted(match.path for match in brace.matches) == ["src/app.py", "src/view.tsx"]
    assert sorted(match.path for match in comma.matches) == ["src/app.py", "src/readme.md"]
    assert [match.path for match in exclude.matches] == ["src/app.py"]


def test_local_sandbox_grep_filters_by_file_type(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "src").mkdir()
    (workspace.path / "src" / "app.py").write_text("needle\n", encoding="utf-8")
    (workspace.path / "src" / "view.tsx").write_text("needle\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    result = client.grep("needle", path="src", file_type="py")

    assert [match.path for match in result.matches] == ["src/app.py"]


def test_local_sandbox_grep_supports_multiline_patterns(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "src").mkdir()
    (workspace.path / "src" / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    single_line = client.grep(r"def run\(\):\n\s+return", path="src")
    multiline = client.grep(r"def run\(\):\n\s+return", path="src", multiline=True)

    assert single_line.matches == []
    assert [(match.line_number, match.line, match.is_match) for match in multiline.matches] == [
        (1, "def run():", True),
        (2, "    return 1", False),
    ]


def test_local_sandbox_grep_includes_context_lines(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "note.txt").write_text("before\nneedle\nafter\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    result = client.grep("needle", context_before=1, context_after=1)

    assert [(match.line_number, match.line, match.is_match) for match in result.matches] == [
        (1, "before", False),
        (2, "needle", True),
        (3, "after", False),
    ]


def test_local_sandbox_glob_finds_files_and_reports_truncation(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "src").mkdir()
    (workspace.path / "src" / "a.py").write_text("a\n", encoding="utf-8")
    (workspace.path / "src" / "b.py").write_text("b\n", encoding="utf-8")
    (workspace.path / "src" / "note.txt").write_text("note\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    result = client.glob("*.py", path="src")
    limited = client.glob("*.py", path="src", max_results=1)

    assert sorted(result.filenames) == ["src/a.py", "src/b.py"]
    assert result.to_dict()["numFiles"] == 2
    assert len(limited.filenames) == 1
    assert limited.truncated is True


def test_local_sandbox_reads_and_greps_utf16le_text_files(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "utf16.txt").write_text("needle\nsecond\n", encoding="utf-16")
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)

    read = client.read_text("utf16.txt")
    result = client.grep("second")

    assert read.content == "needle\nsecond\n"
    assert read.encoding == "utf-16le"
    assert read.line_endings == "lf"
    assert [(match.path, match.line_number, match.line) for match in result.matches] == [
        ("utf16.txt", 2, "second")
    ]


def test_builtin_tools_route_through_sandbox_client(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "note.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(workspace=workspace, sandbox=policy)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        grep = await registry.execute("search.grep", {"pattern": "beta"})
        write = await registry.execute("filesystem.write", {"path": "new.txt", "content": "ok"})
        test_run = await registry.execute(
            "test.run",
            {"command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote("print('tests ok')"))},
        )
        return grep, write, test_run

    grep, write, test_run = asyncio.run(execute())

    assert grep.is_error is False
    assert "note.txt" in grep.content
    assert write.is_error is False
    assert (workspace.path / "new.txt").read_text(encoding="utf-8") == "ok"
    assert test_run.is_error is False
    assert "tests ok" in test_run.content


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is not available on this platform")
def test_builtin_write_rejects_special_files_instead_of_recreating_them(tmp_path):
    workspace = _workspace(tmp_path)
    os.mkfifo(workspace.path / "pipe")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(workspace=workspace, sandbox=policy)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("filesystem.write", {"path": "pipe", "content": "data"}))

    assert result.is_error is True
    assert "refusing to write special file (fifo): pipe" in result.content


def test_sandbox_policy_blocks_escaped_workspace_paths(tmp_path):
    workspace = _workspace(tmp_path)
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    client = LocalSandboxProvider().acquire(workspace, policy)

    try:
        client.write_text("../outside.txt", "no")
    except PermissionError as exc:
        assert "escapes workspace" in str(exc)
    else:
        raise AssertionError("escaped write was not blocked")


def test_sandbox_store_records_leases_and_events(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteSandboxStore(database)
    workspace = _workspace(tmp_path)
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)
    lease = SandboxLeaseRecord.from_lease(client.lease)

    async def persist():
        await store.save_lease(lease)
        await store.record_event(SandboxEventRecord(lease_id=lease.lease_id, event_type="acquired", payload={"tool": "filesystem.read"}))
        await store.save_workspace_snapshot(
            SandboxWorkspaceSnapshotRecord(
                snapshot_id="snapshot-1",
                lease_id=lease.lease_id,
                run_id=lease.run_id,
                phase="before",
                file_count=0,
                total_bytes=0,
            )
        )
        loaded = await store.load_lease(lease.lease_id)
        events = await store.list_events(lease.lease_id)
        snapshots = await store.list_workspace_snapshots_for_run(lease.run_id)
        await store.mark_released(lease.lease_id)
        released = await store.load_lease(lease.lease_id)
        return loaded, events, snapshots, released

    loaded, events, snapshots, released = asyncio.run(persist())

    assert loaded is not None
    assert loaded.provider == "local"
    assert events[0].event_type == "acquired"
    assert snapshots[0].snapshot_id == "snapshot-1"
    assert released is not None
    assert released.status == "released"


def test_sqlite_artifact_store_indexes_run_artifacts(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteArtifactStore(database)
    workspace = _workspace(tmp_path)
    artifact = ArtifactRecord.for_workspace(
        workspace,
        run_id="run-1",
        task_id="task-1",
        tool_call_id="call-1",
        kind="download",
        role="tool_artifact",
        uri=(tmp_path / "control-plane" / "runs" / "run-1" / "artifacts" / "downloads" / "page.html").as_posix(),
        workspace_path="",
        mime_type="text/html",
        size_bytes=12,
        sha256="abc",
    )

    async def persist():
        await store.save_artifact(artifact)
        return await store.list_for_run("run-1")

    records = asyncio.run(persist())

    assert len(records) == 1
    assert records[0].tool_call_id == "call-1"
    assert records[0].workspace_path == ""


def test_in_memory_sandbox_store_records_release(tmp_path):
    store = InMemorySandboxStore()
    workspace = _workspace(tmp_path)
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = LocalSandboxProvider().acquire(workspace, policy)
    lease = SandboxLeaseRecord.from_lease(client.lease)

    async def persist():
        await store.save_lease(lease)
        await store.mark_released(lease.lease_id)
        return await store.load_lease(lease.lease_id)

    loaded = asyncio.run(persist())

    assert loaded is not None
    assert loaded.status == "released"


def test_tool_execution_records_run_scoped_sandbox_events(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.path / "note.txt").write_text("hello", encoding="utf-8")
    store = InMemorySandboxStore()
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(workspace=workspace, sandbox=policy, sandbox_store=store)
    registry = ToolRegistry()
    registry.set_execution_observer(SandboxToolExecutionRecorder(context, store))
    register_builtin_tools(registry, context)

    async def execute():
        results = await registry.execute_many(
            [ToolCall(id="call-1", name="filesystem.read", arguments={"path": "note.txt"})],
            run_id="run-1",
            task_id="task-1",
        )
        lease = await store.load_lease("sandbox_run-1_task-1")
        events = await store.list_events("sandbox_run-1_task-1")
        snapshots = await store.list_workspace_snapshots_for_run("run-1")
        return results, lease, events, snapshots

    results, lease, events, snapshots = asyncio.run(execute())

    assert results[0].is_error is False
    assert results[0].raw["_meta"]["sandbox"]["lease_id"] == "sandbox_run-1_task-1"
    assert lease is not None
    assert lease.run_id == "run-1"
    assert lease.task_id == "task-1"
    assert [event.event_type for event in events] == ["lease_acquired", "tool_started", "tool_finished"]
    assert events[-1].tool_call_id == "call-1"
    assert events[-1].tool_name == "filesystem.read"
    assert events[-1].status == "succeeded"
    assert [snapshot.phase for snapshot in snapshots] == ["before", "after"]
    assert snapshots[-1].diff["file_count_after"] == 1


def test_workspace_snapshot_skips_agent_runtime_state(tmp_path):
    workspace = _workspace(tmp_path)
    internal_log = workspace.path / ".agents" / "runtime" / "runs" / "run-1" / "log.txt"
    internal_log.parent.mkdir(parents=True)
    internal_log.write_text("internal log", encoding="utf-8")
    (workspace.path / "source.py").write_text("print('ok')", encoding="utf-8")

    snapshot = WorkspaceSnapshot.capture(workspace)

    assert "source.py" in snapshot.files
    assert ".agents/runtime/runs/run-1/log.txt" not in snapshot.files


def test_workspace_snapshot_skips_excluded_symlinks_before_resolving(tmp_path):
    workspace = _workspace(tmp_path)
    external_python = tmp_path / "uv" / "python3.11"
    external_python.parent.mkdir(parents=True)
    external_python.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    python_link = workspace.path / ".venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(external_python)

    snapshot = WorkspaceSnapshot.capture(workspace)

    assert ".venv/bin/python" not in snapshot.files


def test_sandbox_profile_defaults_apply_policy(tmp_path):
    workspace = _workspace(tmp_path)

    class AgentConfig:
        SANDBOX_PROFILE = "coding"
        SANDBOX_PROVIDER = "local"
        SANDBOX_IMAGE = ""
        SANDBOX_NETWORK = ""
        SANDBOX_MEMORY = ""
        SANDBOX_CPUS = ""
        SANDBOX_TTL_SECONDS = 0
        SANDBOX_WORKDIR = "/workspace"
        SANDBOX_ALLOW_FILE_WRITE = None
        SANDBOX_ALLOW_PROCESS = None
        SANDBOX_ALLOW_NETWORK = None
        SANDBOX_ALLOWED_COMMANDS = ""

    class Settings:
        agent = AgentConfig()

    profile = sandbox_profile_from_settings(Settings())
    policy = sandbox_policy_from_settings(Settings(), workspace, profile)

    assert profile.name == "coding"
    assert policy.allow_file_write is True
    assert policy.allow_process is True
    assert policy.allow_network is False
    assert "pytest" in policy.allowed_commands


def test_docker_sandbox_provider_mounts_workspace_when_available(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not available")
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode != 0:
        pytest.skip("docker daemon is not available")
    image = os.environ.get("AGENT_TEST_SANDBOX_IMAGE", "python:3.12-slim")
    if subprocess.run(["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode != 0:
        pytest.skip("docker test image is not available locally: %s" % image)
    workspace = _workspace(tmp_path)
    (workspace.path / "note.txt").write_text("hello from docker", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_process=True, allowed_commands=("python3",))

    client = DockerSandboxProvider().acquire(
        workspace,
        policy,
        SandboxProfile(provider="docker", image=image),
        lease_id="sandbox-docker-test",
        metadata={"run_id": "run-docker"},
    )
    read = client.read_text("note.txt")
    result = asyncio.run(client.run_command("python3 -c 'print(123)'"))

    assert read.content == "hello from docker"
    assert result.exit_code == 0
    assert "123" in result.stdout
