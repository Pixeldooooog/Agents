from typer.testing import CliRunner

from agents.entrypoints import agents
from agents.entrypoints.agents import app, _repo_root


def test_agents_entrypoint_resolves_repository_root():
    root = _repo_root()

    assert (root / "apps" / "terminal").is_dir()
    assert (root / "src" / "agents").is_dir()


def test_agents_help_exposes_product_commands_only():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.stdout
    assert "gui" in result.stdout
    assert "doctor" in result.stdout
    assert "terminal" not in result.stdout
    assert "serve" not in result.stdout
    assert "bridge" not in result.stdout


def test_agents_tui_forwards_to_terminal_app(monkeypatch):
    calls = []
    monkeypatch.setenv("BUN", "echo")
    monkeypatch.setattr(agents.subprocess, "call", lambda command, cwd=None, env=None: calls.append((command, cwd, env)) or 0)

    result = CliRunner().invoke(app, ["tui", "--profile", "chat"])

    assert result.exit_code == 0
    command, cwd, env = calls[0]
    assert command[:2] == ["echo", "run"]
    assert "src/main.tsx" in command
    assert command[-2:] == ["--profile", "chat"]
    assert cwd == _repo_root() / "apps" / "terminal"
    assert str(_repo_root() / "src") in env["PYTHONPATH"]


def test_agents_terminal_alias_still_works_hidden(monkeypatch):
    calls = []
    monkeypatch.setenv("BUN", "echo")
    monkeypatch.setattr(agents.subprocess, "call", lambda command, cwd=None, env=None: calls.append((command, cwd, env)) or 0)

    result = CliRunner().invoke(app, ["terminal", "--profile", "chat"])

    assert result.exit_code == 0
    assert calls[0][0][-2:] == ["--profile", "chat"]


def test_makefile_keeps_documented_terminal_aliases():
    makefile = (_repo_root() / "makefile").read_text(encoding="utf-8")

    assert "\nterminal: tui\n" in makefile
    assert "\ncli: tui\n" in makefile
    assert "\nmanual-smoke: terminal-manual-smoke\n" in makefile


def test_find_available_port_skips_busy_port(monkeypatch):
    monkeypatch.setattr(agents, "_port_in_use", lambda host, port: port == 8020)

    port = agents._find_available_port("0.0.0.0", 8020)

    assert port == 8021


def test_connect_host_resolves_wildcard_hosts():
    assert agents._connect_host("0.0.0.0") == "127.0.0.1"
    assert agents._connect_host("::") == "127.0.0.1"
    assert agents._connect_host("localhost") == "localhost"
