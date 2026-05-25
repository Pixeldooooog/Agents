from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.ide import (
    DetectedIDEInfo,
    default_ide_lockfile_dirs,
    detect_ide_lockfiles,
    sorted_ide_lockfiles,
)
from agents.kernel.capabilities.tools.builtin.mcp_management import mcp_configure
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


IDE_DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string", "description": "Workspace path to match against IDE lockfile workspaces."},
        "lockfile_dirs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional directories containing Claude IDE .lock files.",
        },
        "lockfiles": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional explicit IDE lockfile paths. Overrides lockfile_dirs.",
        },
        "include_invalid": {
            "type": "boolean",
            "description": "Include IDE lockfiles whose workspace folders do not match cwd.",
        },
        "port": {
            "type": "integer",
            "description": "Optional IDE MCP port override, matching CLAUDE_CODE_SSE_PORT semantics.",
        },
        "skip_valid_check": {
            "type": "boolean",
            "description": "Treat discovered IDE lockfiles as valid without workspace matching.",
        },
        "host": {
            "type": "string",
            "description": "Optional host override for generated IDE MCP URLs.",
        },
    },
}

MCP_CONFIGURE_IDE_SCHEMA = {
    "type": "object",
    "properties": {
        **IDE_DISCOVERY_SCHEMA["properties"],
        "name": {"type": "string", "description": "MCP server name to save. Defaults to ide."},
        "index": {
            "type": "integer",
            "description": "Explicit detected IDE index to configure when multiple IDEs match.",
        },
    },
}


async def mcp_detect_ide(
    context: ToolRuntimeContext,
    cwd: str = "",
    lockfile_dirs: list[str] | None = None,
    lockfiles: list[str] | None = None,
    include_invalid: bool = False,
    port: int = 0,
    skip_valid_check: bool = False,
    host: str = "",
) -> dict[str, Any]:
    detection = _detect_ide(
        context,
        cwd=cwd,
        lockfile_dirs=lockfile_dirs,
        lockfiles=lockfiles,
        include_invalid=include_invalid,
        port=port,
        skip_valid_check=skip_valid_check,
        host=host,
    )
    return {
        "cwd": str(detection["cwd"]),
        "lockfiles": [str(path) for path in detection["lockfiles"]],
        "detected": [_ide_payload(ide) for ide in detection["detected"]],
        "count": len(detection["detected"]),
    }


async def mcp_configure_ide(
    context: ToolRuntimeContext,
    name: str = "ide",
    cwd: str = "",
    lockfile_dirs: list[str] | None = None,
    lockfiles: list[str] | None = None,
    include_invalid: bool = False,
    port: int = 0,
    skip_valid_check: bool = False,
    host: str = "",
    index: int = -1,
) -> dict[str, Any]:
    detection = _detect_ide(
        context,
        cwd=cwd,
        lockfile_dirs=lockfile_dirs,
        lockfiles=lockfiles,
        include_invalid=include_invalid,
        port=port,
        skip_valid_check=skip_valid_check,
        host=host,
    )
    selected = _select_ide(detection["detected"], port=port, index=index)
    status = await mcp_configure(
        context,
        name=str(name or "ide").strip() or "ide",
        transport=selected.transport,
        url=selected.url,
        auth_token=selected.auth_token or "",
    )
    return {
        **status,
        "selected": _ide_payload(selected),
        "detected": [_ide_payload(ide) for ide in detection["detected"]],
        "lockfiles": [str(path) for path in detection["lockfiles"]],
    }


def _detect_ide(
    context: ToolRuntimeContext,
    *,
    cwd: str,
    lockfile_dirs: list[str] | None,
    lockfiles: list[str] | None,
    include_invalid: bool,
    port: int,
    skip_valid_check: bool,
    host: str,
) -> dict[str, Any]:
    cwd_path = _resolve_workspace_path(context, cwd)
    env_port = _positive_int(port) or _env_port()
    lockfile_paths = _lockfile_paths(context, lockfile_dirs=lockfile_dirs, lockfiles=lockfiles)
    detected = detect_ide_lockfiles(
        lockfile_paths,
        cwd=cwd_path,
        include_invalid=bool(include_invalid),
        env_port=env_port,
        skip_valid_check=bool(skip_valid_check) or _env_truthy("CLAUDE_CODE_IDE_SKIP_VALID_CHECK"),
        host=_host(host),
    )
    return {"cwd": cwd_path, "lockfiles": lockfile_paths, "detected": detected}


def _lockfile_paths(
    context: ToolRuntimeContext,
    *,
    lockfile_dirs: list[str] | None,
    lockfiles: list[str] | None,
) -> list[Path]:
    explicit = _resolve_paths(context, lockfiles)
    if explicit:
        return explicit
    directories = _resolve_paths(context, lockfile_dirs) or default_ide_lockfile_dirs()
    return sorted_ide_lockfiles(directories)


def _resolve_paths(context: ToolRuntimeContext, values: list[str] | str | None) -> list[Path]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = list(values)
    return [_resolve_workspace_path(context, str(value)) for value in raw_values if str(value or "").strip()]


def _resolve_workspace_path(context: ToolRuntimeContext, value: str) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path(context.workspace.path)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path(context.workspace.path) / path
    return path


def _select_ide(detected: list[DetectedIDEInfo], *, port: int, index: int) -> DetectedIDEInfo:
    port_value = _positive_int(port)
    candidates = [ide for ide in detected if ide.port == port_value] if port_value is not None else detected
    if not candidates:
        raise RuntimeError("no IDE MCP lockfiles matched workspace")
    if index >= 0:
        try:
            return candidates[index]
        except IndexError as exc:
            raise IndexError("IDE selection index is out of range") from exc
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError("multiple IDE MCP lockfiles matched workspace; pass port or index")


def _ide_payload(ide: DetectedIDEInfo) -> dict[str, Any]:
    return {
        "name": ide.name,
        "port": ide.port,
        "transport": ide.transport,
        "url": ide.url,
        "workspaceFolders": list(ide.workspace_folders),
        "isValid": ide.is_valid,
        "hasAuthToken": bool(ide.auth_token),
        "ideRunningInWindows": ide.ide_running_in_windows,
    }


def _host(value: str) -> str:
    return str(value or os.environ.get("CLAUDE_CODE_IDE_HOST_OVERRIDE") or "").strip()


def _env_port() -> int | None:
    return _positive_int(os.environ.get("CLAUDE_CODE_SSE_PORT"))


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}
