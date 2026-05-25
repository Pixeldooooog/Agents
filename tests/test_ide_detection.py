import time
from pathlib import Path

from agents.kernel.capabilities.ide import (
    IDE_AUTH_HEADER,
    detect_ide_lockfiles,
    mcp_record_from_detected_ide,
    read_ide_lockfile,
    sorted_ide_lockfiles,
)
from agents.kernel.context.workspace import WorkspaceContext


def test_read_ide_lockfile_accepts_src_origin_json_format(tmp_path: Path):
    lockfile = tmp_path / "32101.lock"
    lockfile.write_text(
        """
{
  "workspaceFolders": ["/repo"],
  "pid": 123,
  "ideName": "VS Code",
  "transport": "ws",
  "runningInWindows": true,
  "authToken": "ide-token"
}
""".strip(),
        encoding="utf-8",
    )

    info = read_ide_lockfile(lockfile)

    assert info is not None
    assert info.workspace_folders == ["/repo"]
    assert info.port == 32101
    assert info.pid == 123
    assert info.ide_name == "VS Code"
    assert info.use_websocket is True
    assert info.running_in_windows is True
    assert info.auth_token == "ide-token"


def test_read_ide_lockfile_accepts_legacy_workspace_list(tmp_path: Path):
    lockfile = tmp_path / "32100.lock"
    lockfile.write_text("/repo\n /other/repo \n", encoding="utf-8")

    info = read_ide_lockfile(lockfile)

    assert info is not None
    assert info.workspace_folders == ["/repo", "/other/repo"]
    assert info.port == 32100
    assert info.use_websocket is False


def test_sorted_ide_lockfiles_returns_newest_first_and_skips_missing_dirs(tmp_path: Path):
    old = tmp_path / "3000.lock"
    new = tmp_path / "3001.lock"
    ignored = tmp_path / "notes.txt"
    old.write_text("old", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")
    time.sleep(0.01)
    new.write_text("new", encoding="utf-8")

    lockfiles = sorted_ide_lockfiles([tmp_path / "missing", tmp_path])

    assert lockfiles == [new, old]


def test_detect_ide_lockfiles_matches_current_workspace_and_builds_urls(tmp_path: Path):
    workspace = tmp_path / "repo"
    nested = workspace / "pkg"
    nested.mkdir(parents=True)
    sse_lockfile = tmp_path / "32100.lock"
    ws_lockfile = tmp_path / "32101.lock"
    sse_lockfile.write_text('{"workspaceFolders":["%s"],"ideName":"Cursor"}' % workspace, encoding="utf-8")
    ws_lockfile.write_text(
        '{"workspaceFolders":["/other"],"ideName":"VS Code","transport":"ws","authToken":"token"}',
        encoding="utf-8",
    )

    detected = detect_ide_lockfiles(
        [sse_lockfile, ws_lockfile],
        cwd=nested,
        include_invalid=True,
        host="localhost",
    )

    assert [(ide.name, ide.port, ide.transport, ide.is_valid) for ide in detected] == [
        ("Cursor", 32100, "sse-ide", True),
        ("VS Code", 32101, "ws-ide", False),
    ]
    assert detected[0].url == "http://localhost:32100/sse"
    assert detected[1].url == "ws://localhost:32101"
    assert detected[1].auth_token == "token"


def test_detect_ide_lockfiles_filters_invalid_and_prefers_single_env_port(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    first = tmp_path / "32100.lock"
    second = tmp_path / "32101.lock"
    first.write_text('{"workspaceFolders":["%s"],"ideName":"Cursor"}' % workspace, encoding="utf-8")
    second.write_text('{"workspaceFolders":["%s"],"ideName":"VS Code"}' % workspace, encoding="utf-8")

    detected = detect_ide_lockfiles([first, second], cwd=workspace, env_port=32101)

    assert len(detected) == 1
    assert detected[0].name == "VS Code"
    assert detected[0].port == 32101


def test_mcp_record_from_detected_ide_preserves_ws_auth_token(tmp_path: Path):
    workspace_path = tmp_path / "repo"
    workspace_path.mkdir()
    lockfile = tmp_path / "32101.lock"
    lockfile.write_text(
        '{"workspaceFolders":["%s"],"ideName":"VS Code","transport":"ws","authToken":"ide-token"}'
        % workspace_path,
        encoding="utf-8",
    )
    ide = detect_ide_lockfiles([lockfile], cwd=workspace_path)[0]
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )

    record = mcp_record_from_detected_ide(ide, workspace=workspace)

    assert record.name == "ide"
    assert record.transport == "ws-ide"
    assert record.url == "ws://127.0.0.1:32101"
    assert record.headers == {IDE_AUTH_HEADER: "ide-token"}
    assert record.tenant_id == "tenant"
    assert record.workspace_id == "workspace"
