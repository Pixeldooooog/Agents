import json

from agents.interfaces.server.api.agent.operation_frames import build_operation_frames
from agents.kernel.capabilities.sandbox.records import SandboxEventRecord, SandboxWorkspaceSnapshotRecord
from agents.kernel.schema import RuntimeEvent


def test_operation_frames_project_runtime_contract_events():
    frames = build_operation_frames(
        run_id="run-1",
        runtime_events=[
            RuntimeEvent(
                type="tool_start",
                name="filesystem.write",
                payload={
                    "id": "call-1",
                    "name": "filesystem.write",
                    "arguments": {"path": "notes.md", "content": "hello"},
                    "contract": {
                        "activity": {"kind": "edit", "title": "Write file", "target_argument": "path"},
                        "target": "notes.md",
                        "paths": ["notes.md"],
                        "metadata": {"writes_state": True},
                    },
                },
            ),
            RuntimeEvent(
                type="tool_result",
                name="filesystem.write",
                payload={
                    "tool_call_id": "call-1",
                    "content": '{"path":"notes.md"}',
                    "raw": {"path": "notes.md", "bytes": 5},
                    "contract": {
                        "activity": {"kind": "edit", "title": "Write file", "target_argument": "path"},
                        "target": "notes.md",
                        "paths": ["notes.md"],
                        "metadata": {"writes_state": True},
                    },
                },
            ),
        ],
        sandbox_events=[],
        sandbox_snapshots=[],
        artifacts=[],
    )

    assert [frame["phase"] for frame in frames] == ["opening", "done"]
    assert frames[0]["source"] == "runtime_contract"
    assert frames[0]["scene"] == "edit"
    assert frames[0]["target"] == "notes.md"
    assert frames[0]["files"] == [{"path": "notes.md", "status": "target"}]
    assert frames[1]["resultPreview"] == {"path": "notes.md", "bytes": 5}


def test_operation_frames_expand_sandbox_tool_events():
    started = SandboxEventRecord(
        lease_id="lease-1",
        event_type="tool_started",
        run_id="run-1",
        tool_call_id="call-1",
        tool_name="filesystem.write",
        status="running",
        payload={"arguments": json.dumps({"path": "notes.md", "content": "hello"})},
        created_at=1.0,
    )
    finished = SandboxEventRecord(
        lease_id="lease-1",
        event_type="tool_finished",
        run_id="run-1",
        tool_call_id="call-1",
        tool_name="filesystem.write",
        status="succeeded",
        duration_ms=12.5,
        payload={
            "arguments": json.dumps({"path": "notes.md", "content": "hello"}),
            "result": json.dumps({"path": "notes.md", "bytes": 5}),
        },
        created_at=2.0,
    )
    snapshot = SandboxWorkspaceSnapshotRecord(
        snapshot_id="snap-1",
        lease_id="lease-1",
        run_id="run-1",
        phase="after",
        diff={"created": ["notes.md"], "modified": [], "deleted": []},
        created_at=1.5,
    )

    frames = build_operation_frames(
        run_id="run-1",
        sandbox_events=[started, finished],
        sandbox_snapshots=[snapshot],
        artifacts=[],
    )

    assert [frame["phase"] for frame in frames] == ["opening", "running", "closing", "done"]
    assert frames[0]["scene"] == "edit"
    assert frames[1]["step"]["label"] == "edit file"
    assert frames[-1]["files"] == [{"path": "notes.md", "status": "created"}]
    assert frames[-1]["stats"]["duration_ms"] == 12.5
