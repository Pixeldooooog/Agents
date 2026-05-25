from agents.kernel.capabilities.ide_extension import (
    IDE_EXTENSION_ID,
    IDECommandResult,
    ide_extension_status,
    install_ide_extension,
    installed_vscode_extension_version,
    installation_env,
    vscode_ide_command,
    vscode_ide_command_from_parent_process,
)


def test_installed_vscode_extension_version_parses_exact_extension():
    stdout = "\n".join(
        [
            "anthropic.claude-code-insiders@9.9.9",
            "anthropic.claude-code@1.2.3",
            "other.extension@0.1.0",
        ]
    )

    assert installed_vscode_extension_version(stdout) == "1.2.3"


def test_vscode_command_uses_windows_cmd_wrapper():
    assert vscode_ide_command("vscode", platform="windows") == "code.cmd"
    assert vscode_ide_command("cursor", platform="windows") == "cursor.cmd"
    assert vscode_ide_command("windsurf", platform="linux") == "windsurf"


def test_vscode_command_from_parent_process_matches_macos_app_bundle():
    command = "/Applications/Cursor.app/Contents/MacOS/Electron --type=renderer"

    assert (
        vscode_ide_command_from_parent_process([command], platform="darwin")
        == "/Applications/Cursor.app/Contents/Resources/app/bin/cursor"
    )


def test_ide_extension_status_reports_vscode_installation():
    calls = []

    def runner(command, args, env):
        calls.append((command, args, env))
        return IDECommandResult(code=0, stdout=f"{IDE_EXTENSION_ID}@1.2.3\n")

    status = ide_extension_status("vscode", runner=runner, platform="linux")

    assert status.installed is True
    assert status.installed_version == "1.2.3"
    assert status.command == "code"
    assert calls[0][0] == "code"
    assert calls[0][1] == ["--list-extensions", "--show-versions"]
    assert calls[0][2]["DISPLAY"] == ""


def test_install_ide_extension_skips_current_or_newer_version():
    calls = []

    def runner(command, args, env):
        calls.append((command, args, env))
        return IDECommandResult(code=0, stdout=f"{IDE_EXTENSION_ID}@2.0.0\n")

    status = install_ide_extension("cursor", target_version="1.9.0", runner=runner, platform="darwin")

    assert status.installed is True
    assert status.installed_version == "2.0.0"
    assert [args for _command, args, _env in calls] == [["--list-extensions", "--show-versions"]]


def test_install_ide_extension_runs_force_install_when_missing_or_old():
    calls = []

    def runner(command, args, env):
        calls.append((command, args, env))
        if args == ["--list-extensions", "--show-versions"]:
            return IDECommandResult(code=0, stdout=f"{IDE_EXTENSION_ID}@1.0.0\n")
        return IDECommandResult(code=0, stdout="")

    status = install_ide_extension("windsurf", target_version="1.2.0", runner=runner, platform="darwin")

    assert status.installed is True
    assert status.installed_version == "1.2.0"
    assert [args for _command, args, _env in calls] == [
        ["--list-extensions", "--show-versions"],
        ["--force", "--install-extension", IDE_EXTENSION_ID],
    ]


def test_install_ide_extension_reports_jetbrains_manual_boundary():
    status = install_ide_extension("pycharm")

    assert status.installed is False
    assert status.install_supported is False
    assert status.skipped_reason == "jetbrains-extension-install-manual"


def test_installation_env_clears_display_only_on_linux():
    assert installation_env(platform="linux", environ={"DISPLAY": ":0", "PATH": "/bin"}) == {
        "DISPLAY": "",
        "PATH": "/bin",
    }
    assert installation_env(platform="darwin", environ={"DISPLAY": ":0"}) is None
