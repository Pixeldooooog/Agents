from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Callable, Mapping

from agents.kernel.capabilities.ide_environment import detect_ide_platform


IDE_EXTENSION_ID = "anthropic.claude-code"
JETBRAINS_IDES = {
    "androidstudio",
    "appcode",
    "aqua",
    "clion",
    "datagrip",
    "dataspell",
    "fleet",
    "gateway",
    "goland",
    "intellij",
    "jetbrains",
    "phpstorm",
    "pycharm",
    "rider",
    "rubymine",
    "webstorm",
}
VSCODE_IDE_COMMANDS = {
    "cursor": "cursor",
    "vscode": "code",
    "windsurf": "windsurf",
}


@dataclass(frozen=True)
class IDECommandResult:
    code: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""


@dataclass(frozen=True)
class IDEExtensionStatus:
    ide_type: str
    installed: bool
    install_supported: bool
    command: str = ""
    extension_id: str = IDE_EXTENSION_ID
    installed_version: str | None = None
    error: str | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ideType": self.ide_type,
            "installed": self.installed,
            "installSupported": self.install_supported,
            "command": self.command,
            "extensionId": self.extension_id,
            "installedVersion": self.installed_version,
            "error": self.error,
            "skippedReason": self.skipped_reason,
        }


CommandRunner = Callable[[str, list[str], Mapping[str, str] | None], IDECommandResult]


def ide_extension_status(
    ide_type: str,
    *,
    runner: CommandRunner | None = None,
    platform: str | None = None,
    parent_command_lines: list[str] | None = None,
) -> IDEExtensionStatus:
    ide = _ide_type(ide_type)
    if ide in JETBRAINS_IDES:
        return IDEExtensionStatus(
            ide_type=ide,
            installed=False,
            install_supported=False,
            skipped_reason="jetbrains-extension-install-manual",
        )
    command = vscode_ide_command(ide, platform=platform, parent_command_lines=parent_command_lines)
    if not command:
        return IDEExtensionStatus(
            ide_type=ide,
            installed=False,
            install_supported=False,
            skipped_reason="unsupported-ide",
        )
    result = (runner or run_ide_command)(
        command,
        ["--list-extensions", "--show-versions"],
        installation_env(platform=platform),
    )
    if result.code != 0:
        return IDEExtensionStatus(
            ide_type=ide,
            installed=False,
            install_supported=True,
            command=command,
            error=_command_error(result),
        )
    installed_version = installed_vscode_extension_version(result.stdout)
    return IDEExtensionStatus(
        ide_type=ide,
        installed=installed_version is not None,
        install_supported=True,
        command=command,
        installed_version=installed_version,
    )


def install_ide_extension(
    ide_type: str,
    *,
    target_version: str = "",
    runner: CommandRunner | None = None,
    platform: str | None = None,
    parent_command_lines: list[str] | None = None,
) -> IDEExtensionStatus:
    status = ide_extension_status(
        ide_type,
        runner=runner,
        platform=platform,
        parent_command_lines=parent_command_lines,
    )
    if not status.install_supported or not status.command:
        return status
    target = str(target_version or _package_version()).strip()
    if status.installed_version and not _is_older_version(status.installed_version, target):
        return status

    result = (runner or run_ide_command)(
        status.command,
        ["--force", "--install-extension", IDE_EXTENSION_ID],
        installation_env(platform=platform),
    )
    if result.code != 0:
        return IDEExtensionStatus(
            ide_type=status.ide_type,
            installed=False,
            install_supported=True,
            command=status.command,
            installed_version=status.installed_version,
            error=_command_error(result),
        )
    return IDEExtensionStatus(
        ide_type=status.ide_type,
        installed=True,
        install_supported=True,
        command=status.command,
        installed_version=target,
    )


def vscode_ide_command(
    ide_type: str,
    *,
    platform: str | None = None,
    parent_command_lines: list[str] | None = None,
) -> str:
    platform_name = detect_ide_platform(platform)
    parent_command = vscode_ide_command_from_parent_process(
        parent_command_lines or [],
        platform=platform_name,
    )
    if parent_command:
        return parent_command
    command = VSCODE_IDE_COMMANDS.get(_ide_type(ide_type), "")
    if command and platform_name == "windows":
        return command + ".cmd"
    return command


def vscode_ide_command_from_parent_process(
    command_lines: list[str],
    *,
    platform: str | None = None,
) -> str:
    platform_name = detect_ide_platform(platform)
    if platform_name not in {"darwin", "macos"}:
        return ""
    app_names = {
        "Cursor.app": "cursor",
        "Visual Studio Code - Insiders.app": "code",
        "Visual Studio Code.app": "code",
        "VSCodium.app": "codium",
        "Windsurf.app": "windsurf",
    }
    executable_suffix = "/Contents/MacOS/Electron"
    for command_line in command_lines:
        text = str(command_line or "")
        for app_name, executable_name in app_names.items():
            marker = app_name + executable_suffix
            app_index = text.find(marker)
            if app_index == -1:
                continue
            folder_end = app_index + len(app_name)
            return text[:folder_end] + "/Contents/Resources/app/bin/" + executable_name
    return ""


def installed_vscode_extension_version(stdout: str, extension_id: str = IDE_EXTENSION_ID) -> str | None:
    for line in str(stdout or "").splitlines():
        item, separator, item_version = line.partition("@")
        if separator and item == extension_id and item_version:
            return item_version.strip()
        if not separator and item == extension_id:
            return ""
    return None


def installation_env(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    if detect_ide_platform(platform) != "linux":
        return None
    env = dict(environ or os.environ)
    env["DISPLAY"] = ""
    return env


def run_ide_command(command: str, args: list[str], env: Mapping[str, str] | None = None) -> IDECommandResult:
    try:
        result = subprocess.run(
            [command, *args],
            check=False,
            capture_output=True,
            env=dict(env) if env is not None else None,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return IDECommandResult(code=1, error=str(exc))
    return IDECommandResult(
        code=int(result.returncode or 0),
        stdout=str(result.stdout or ""),
        stderr=str(result.stderr or ""),
    )


def _ide_type(value: str) -> str:
    ide = str(value or "").strip().lower()
    if not ide:
        raise ValueError("ide_type is required")
    return ide


def _command_error(result: IDECommandResult) -> str:
    return " ".join(part for part in [str(result.code), result.error, result.stderr] if part).strip()


def _package_version() -> str:
    try:
        return version("agents")
    except PackageNotFoundError:
        return "0.1.0"


def _is_older_version(current: str, target: str) -> bool:
    current_parts = _version_parts(current)
    target_parts = _version_parts(target)
    width = max(len(current_parts), len(target_parts), 1)
    return current_parts + [0] * (width - len(current_parts)) < target_parts + [0] * (width - len(target_parts))


def _version_parts(value: str) -> list[int]:
    parts: list[int] = []
    for item in str(value or "").split("."):
        digits = ""
        for character in item:
            if not character.isdigit():
                break
            digits += character
        parts.append(int(digits or 0))
    return parts
