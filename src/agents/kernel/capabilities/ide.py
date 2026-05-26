from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Collection, Iterable

from agents.kernel.capabilities.ide_environment import (
    detect_ide_host,
    detect_ide_platform,
    is_inside_ide_workspace,
    should_keep_ide_lockfile_for_process,
)
from agents.kernel.mcp.config import MCPServerRecord, server_record_for_scope


IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"
ProcessChecker = Callable[[int], bool]


def default_ide_lockfile_dirs(config_dir: str | Path | None = None) -> list[Path]:
    base_dir = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    return [base_dir / "ide"]


@dataclass(frozen=True)
class IDELockfileInfo:
    workspace_folders: list[str] = field(default_factory=list)
    port: int = 0
    pid: int | None = None
    ide_name: str | None = None
    use_websocket: bool = False
    running_in_windows: bool = False
    auth_token: str | None = None
    path: str = ""


@dataclass(frozen=True)
class DetectedIDEInfo:
    name: str
    port: int
    workspace_folders: list[str]
    url: str
    transport: str
    is_valid: bool
    auth_token: str | None = None
    ide_running_in_windows: bool = False


def sorted_ide_lockfiles(directories: Iterable[str | Path]) -> list[Path]:
    entries: list[tuple[float, Path]] = []
    for directory in directories:
        root = Path(directory).expanduser()
        try:
            for item in root.iterdir():
                if not item.name.endswith(".lock"):
                    continue
                try:
                    entries.append((item.stat().st_mtime, item))
                except OSError:
                    continue
        except OSError:
            continue
    return [path for _mtime, path in sorted(entries, key=lambda item: item[0], reverse=True)]


def read_ide_lockfile(path: str | Path) -> IDELockfileInfo | None:
    lockfile = Path(path).expanduser()
    try:
        port = _port_from_lockfile(lockfile)
        if port is None:
            return None
        content = lockfile.read_text(encoding="utf-8")
    except OSError:
        return None

    payload = _parse_lockfile_content(content)
    return IDELockfileInfo(
        workspace_folders=payload["workspace_folders"],
        port=port,
        pid=payload["pid"],
        ide_name=payload["ide_name"],
        use_websocket=payload["use_websocket"],
        running_in_windows=payload["running_in_windows"],
        auth_token=payload["auth_token"],
        path=str(lockfile),
    )


def detect_ide_lockfiles(
    lockfiles: Iterable[str | Path],
    *,
    cwd: str | Path,
    include_invalid: bool = False,
    env_port: int | None = None,
    skip_valid_check: bool = False,
    host: str = "",
    platform: str | None = None,
    wsl_distro_name: str | None = None,
    terminal_name: str | None = None,
    force_code_terminal: bool | None = None,
    parent_pid: int | None = None,
    ancestor_pids: Collection[int] | None = None,
    process_checker: ProcessChecker | None = None,
    fallback_name: str = "IDE",
) -> list[DetectedIDEInfo]:
    platform_name = detect_ide_platform(platform)
    detected: list[DetectedIDEInfo] = []
    for lockfile in lockfiles:
        info = read_ide_lockfile(lockfile)
        if info is None:
            continue
        is_valid = (
            skip_valid_check
            or (env_port is not None and info.port == env_port)
            or any(
                is_inside_ide_workspace(
                    cwd,
                    folder,
                    platform=platform_name,
                    running_in_windows=info.running_in_windows,
                    wsl_distro_name=wsl_distro_name
                    or os.environ.get("WSL_DISTRO_NAME"),
                )
                for folder in info.workspace_folders
            )
        )
        if not is_valid and not include_invalid:
            continue
        env_port_matches = env_port is not None and info.port == env_port
        if not should_keep_ide_lockfile_for_process(
            lockfile_pid=info.pid,
            env_port_matches=env_port_matches,
            platform=platform_name,
            terminal_name=terminal_name,
            parent_pid=parent_pid,
            ancestor_pids=ancestor_pids,
            process_checker=process_checker,
            force_code_terminal=force_code_terminal,
        ):
            continue
        detected.append(
            _detected_ide(
                info,
                host=host,
                platform=platform_name,
                is_valid=is_valid,
                fallback_name=fallback_name,
            )
        )

    if not include_invalid and env_port is not None:
        env_matches = [ide for ide in detected if ide.is_valid and ide.port == env_port]
        if len(env_matches) == 1:
            return env_matches
    return detected


def mcp_record_from_detected_ide(
    ide: DetectedIDEInfo,
    *,
    workspace: Any,
    name: str = "ide",
) -> MCPServerRecord:
    headers = {}
    if ide.transport == "ws-ide" and ide.auth_token:
        headers[IDE_AUTH_HEADER] = ide.auth_token
    return server_record_for_scope(
        name=name,
        workspace=workspace,
        command="",
        transport=ide.transport,
        url=ide.url,
        headers=headers,
    )


def _detected_ide(
    info: IDELockfileInfo,
    *,
    host: str,
    platform: str,
    is_valid: bool,
    fallback_name: str,
) -> DetectedIDEInfo:
    transport = "ws-ide" if info.use_websocket else "sse-ide"
    resolved_host = detect_ide_host(
        running_in_windows=info.running_in_windows,
        port=info.port,
        host_override=host,
        platform=platform,
    )
    url = (
        "ws://%s:%s" % (resolved_host, info.port)
        if info.use_websocket
        else "http://%s:%s/sse" % (resolved_host, info.port)
    )
    return DetectedIDEInfo(
        name=info.ide_name or fallback_name,
        port=info.port,
        workspace_folders=list(info.workspace_folders),
        url=url,
        transport=transport,
        is_valid=is_valid,
        auth_token=info.auth_token,
        ide_running_in_windows=info.running_in_windows,
    )


def _parse_lockfile_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {
            "workspace_folders": [line.strip() for line in content.splitlines()],
            "pid": None,
            "ide_name": None,
            "use_websocket": False,
            "running_in_windows": False,
            "auth_token": None,
        }
    if not isinstance(parsed, dict):
        parsed = {}
    workspace_folders = parsed.get("workspaceFolders")
    return {
        "workspace_folders": [str(item) for item in workspace_folders] if isinstance(workspace_folders, list) else [],
        "pid": int(parsed["pid"]) if isinstance(parsed.get("pid"), int) else None,
        "ide_name": str(parsed["ideName"]) if isinstance(parsed.get("ideName"), str) else None,
        "use_websocket": parsed.get("transport") == "ws",
        "running_in_windows": parsed.get("runningInWindows") is True,
        "auth_token": str(parsed["authToken"]) if isinstance(parsed.get("authToken"), str) else None,
    }


def _port_from_lockfile(path: Path) -> int | None:
    name = path.name
    if not name.endswith(".lock"):
        return None
    try:
        return int(name.removesuffix(".lock"))
    except ValueError:
        return None
