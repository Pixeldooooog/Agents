from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}

app = typer.Typer(
    add_completion=False,
    context_settings=CONTEXT,
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    """Launch the TUI app by default."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(_run_tui(list(ctx.args)))


@app.command(context_settings=CONTEXT)
def tui(ctx: typer.Context) -> None:
    """Launch the local TUI."""
    raise typer.Exit(_run_tui(list(ctx.args)))


@app.command(context_settings=CONTEXT, hidden=True)
def terminal(ctx: typer.Context) -> None:
    """Compatibility alias for tui."""
    raise typer.Exit(_run_tui(list(ctx.args)))


@app.command()
def gui(
    build: bool = typer.Option(True, "--build/--no-build", help="Build apps/web/dist when it is missing."),
) -> None:
    """Launch the local web interface."""
    raise typer.Exit(_run_gui(build=build))


@app.command(hidden=True)
def serve() -> None:
    """Run the HTTP/SSE service process."""
    from agents.interfaces.server.__main__ import main as server_main

    server_main()


@app.command("bridge", context_settings=CONTEXT, hidden=True)
def bridge_command(ctx: typer.Context) -> None:
    """Run the internal terminal bridge."""
    from agents.interfaces.bridge.ndjson import main as bridge_main

    bridge_main(list(ctx.args))


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")) -> None:
    """Check local readiness without leaking credentials."""
    from agents.entrypoints.doctor import main as doctor_main

    raise typer.Exit(doctor_main(json_output=json_output))


def main() -> None:
    app()


def _run_tui(args: list[str]) -> int:
    repo_root = _repo_root()
    terminal_dir = repo_root / "apps" / "terminal"
    bun = os.environ.get("BUN", "bun")
    env = os.environ.copy()
    env["PYTHONPATH"] = _merge_pythonpath(str(repo_root / "src"), env.get("PYTHONPATH", ""))
    command = [
        bun,
        "run",
        "src/main.tsx",
        "--repo-root",
        str(repo_root),
        "--python",
        sys.executable,
        *args,
    ]
    try:
        return subprocess.call(command, cwd=terminal_dir, env=env)
    except FileNotFoundError:
        typer.echo("bun is required for the TUI. Install bun or run make bridge-fallback.", err=True)
        return 127


def _run_gui(*, build: bool = True) -> int:
    repo_root = _repo_root()
    ready = _ensure_web_dist(repo_root, build=build)
    if ready != 0:
        return ready
    from agents.interfaces.server.__main__ import main as server_main
    from agents.interfaces.server.core.config import settings

    typer.echo("GUI: %s/ui/" % str(getattr(settings.server, "DOMAIN", "http://localhost:8010")).rstrip("/"))
    server_main(show_settings=False)
    return 0


def _ensure_web_dist(repo_root: Path, *, build: bool = True) -> int:
    web_dir = repo_root / "apps" / "web"
    index = web_dir / "dist" / "index.html"
    if index.is_file():
        return 0
    if not build:
        typer.echo("apps/web/dist is missing. Run `cd apps/web && npm run build`.", err=True)
        return 1
    npm = os.environ.get("NPM", "npm")
    try:
        return subprocess.call([npm, "run", "build"], cwd=web_dir)
    except FileNotFoundError:
        typer.echo("npm is required to build the GUI. Install npm or run `agents gui --no-build` after building apps/web/dist.", err=True)
        return 127


def _merge_pythonpath(first: str, existing: str) -> str:
    return first if not existing else os.pathsep.join([first, existing])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    main()
