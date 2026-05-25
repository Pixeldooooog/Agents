from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from agents.kernel.mcp_config import MCPServerRecord, server_record_for_scope


IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"


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
    host: str = "127.0.0.1",
    fallback_name: str = "IDE",
) -> list[DetectedIDEInfo]:
    cwd_text = _normalize_path(cwd)
    detected: list[DetectedIDEInfo] = []
    for lockfile in lockfiles:
        info = read_ide_lockfile(lockfile)
        if info is None:
            continue
        is_valid = (
            skip_valid_check
            or (env_port is not None and info.port == env_port)
            or any(_is_inside_workspace(cwd_text, folder) for folder in info.workspace_folders)
        )
        if not is_valid and not include_invalid:
            continue
        detected.append(_detected_ide(info, host=host, is_valid=is_valid, fallback_name=fallback_name))

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
    is_valid: bool,
    fallback_name: str,
) -> DetectedIDEInfo:
    transport = "ws-ide" if info.use_websocket else "sse-ide"
    url = "ws://%s:%s" % (host, info.port) if info.use_websocket else "http://%s:%s/sse" % (host, info.port)
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


def _is_inside_workspace(cwd: str, workspace_folder: str) -> bool:
    if not workspace_folder:
        return False
    workspace = _normalize_path(workspace_folder)
    return cwd == workspace or cwd.startswith(workspace + "/")


def _normalize_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    return unicodedata.normalize("NFC", str(resolved)).replace("\\", "/").rstrip("/")
