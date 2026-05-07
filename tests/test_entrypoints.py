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
