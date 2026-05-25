from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Callable


ConnectChecker = Callable[[str, int, float], bool]


def detect_ide_platform(platform: str | None = None) -> str:
    if platform:
        return str(platform).strip().lower()
    if os.name == "nt":
        return "windows"
    if os.environ.get("WSL_DISTRO_NAME"):
        return "wsl"
    if sys.platform.startswith("linux") and _linux_proc_version_mentions_wsl():
        return "wsl"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def is_inside_ide_workspace(
    cwd: str | Path,
    workspace_folder: str,
    *,
    platform: str | None = None,
    running_in_windows: bool = False,
    wsl_distro_name: str | None = None,
) -> bool:
    platform_name = detect_ide_platform(platform)
    cwd_path = normalize_ide_path(cwd, platform=platform_name)
    for candidate in _workspace_candidates(
        workspace_folder,
        platform=platform_name,
        running_in_windows=running_in_windows,
        wsl_distro_name=wsl_distro_name,
    ):
        workspace = normalize_ide_path(candidate, platform=platform_name)
        if _path_contains(cwd_path, workspace, platform=platform_name):
            return True
    return False


def normalize_ide_path(path: str | Path, *, platform: str | None = None) -> str:
    text = unicodedata.normalize("NFC", str(path)).strip()
    if not text:
        return ""
    platform_name = detect_ide_platform(platform)
    if platform_name == "windows" or _looks_like_windows_drive_path(text):
        return _normalize_windows_path_text(text)
    if text.startswith("\\\\"):
        return text.replace("\\", "/").rstrip("/")
    resolved = Path(text).expanduser().resolve(strict=False)
    return unicodedata.normalize("NFC", str(resolved)).replace("\\", "/").rstrip("/")


def windows_path_to_wsl_path(windows_path: str, *, wsl_distro_name: str | None = None) -> str:
    if not windows_path:
        return windows_path

    unc_match = _wsl_unc_match(windows_path)
    if unc_match:
        distro, suffix = unc_match
        if wsl_distro_name and distro != wsl_distro_name:
            return windows_path
        local = suffix.replace("\\", "/").strip("/")
        return "/" + local if local else "/"

    drive_match = re.match(r"^([a-zA-Z]):[\\/]*(.*)$", windows_path)
    if drive_match:
        drive = drive_match.group(1).lower()
        suffix = drive_match.group(2).replace("\\", "/").strip("/")
        return "/mnt/%s/%s" % (drive, suffix) if suffix else "/mnt/%s" % drive

    return windows_path.replace("\\", "/")


def wsl_distro_matches(windows_path: str, wsl_distro_name: str | None) -> bool:
    if not wsl_distro_name:
        return True
    unc_match = _wsl_unc_match(windows_path)
    return unc_match is None or unc_match[0] == wsl_distro_name


def detect_ide_host(
    *,
    running_in_windows: bool,
    port: int,
    host_override: str = "",
    platform: str | None = None,
    route_text: str | None = None,
    connect_checker: ConnectChecker | None = None,
    timeout_seconds: float = 0.5,
) -> str:
    override = str(
        host_override or os.environ.get("CLAUDE_CODE_IDE_HOST_OVERRIDE") or "",
    ).strip()
    if override:
        return override
    if detect_ide_platform(platform) != "wsl" or not running_in_windows:
        return "127.0.0.1"

    gateway = default_gateway_from_route_text(route_text) if route_text is not None else _default_gateway_ip()
    checker = connect_checker or _can_connect
    if gateway and checker(gateway, int(port), timeout_seconds):
        return gateway
    return "127.0.0.1"


def default_gateway_from_route_text(route_text: str | None) -> str | None:
    text = str(route_text or "")
    for line in text.splitlines():
        match = re.search(
            r"\bdefault\s+via\s+(\d+\.\d+\.\d+\.\d+)\b",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)

    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] != "00000000":
            continue
        try:
            raw = bytes.fromhex(parts[2])
        except ValueError:
            continue
        if len(raw) == 4:
            return socket.inet_ntoa(raw[::-1])
    return None


def _workspace_candidates(
    workspace_folder: str,
    *,
    platform: str,
    running_in_windows: bool,
    wsl_distro_name: str | None,
) -> list[str]:
    if not workspace_folder:
        return []
    if platform != "wsl" or not running_in_windows:
        return [workspace_folder]
    if not wsl_distro_matches(workspace_folder, wsl_distro_name):
        return []
    converted = windows_path_to_wsl_path(workspace_folder, wsl_distro_name=wsl_distro_name)
    return _unique([workspace_folder, converted])


def _path_contains(cwd: str, workspace: str, *, platform: str) -> bool:
    if not cwd or not workspace:
        return False
    if workspace == "/":
        return cwd.startswith("/")
    cwd_value = cwd.casefold() if platform == "windows" else cwd
    workspace_value = workspace.casefold() if platform == "windows" else workspace
    return cwd_value == workspace_value or cwd_value.startswith(workspace_value + "/")


def _normalize_windows_path_text(path: str) -> str:
    text = path.replace("\\", "/").rstrip("/")
    return re.sub(r"^([a-zA-Z]):", lambda match: match.group(1).upper() + ":", text)


def _looks_like_windows_drive_path(path: str) -> bool:
    return re.match(r"^[a-zA-Z]:[\\/]", path) is not None


def _wsl_unc_match(path: str) -> tuple[str, str] | None:
    match = re.match(r"^\\\\wsl(?:\.localhost|\$)\\([^\\]+)(.*)$", path)
    if not match:
        return None
    return match.group(1), match.group(2)


def _default_gateway_ip() -> str | None:
    try:
        result = subprocess.run(
            ["ip", "route", "show"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0:
        gateway = default_gateway_from_route_text(result.stdout)
        if gateway:
            return gateway

    try:
        route_table = Path("/proc/net/route").read_text(encoding="utf-8")
    except OSError:
        return None
    return default_gateway_from_route_text(route_table)


def _can_connect(host: str, port: int, timeout_seconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _linux_proc_version_mentions_wsl() -> bool:
    try:
        version = Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl" in version


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
