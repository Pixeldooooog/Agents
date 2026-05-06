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
    """Launch the terminal app by default."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(_run_terminal(list(ctx.args)))


@app.command(context_settings=CONTEXT)
def terminal(ctx: typer.Context) -> None:
    """Launch the terminal app."""
    raise typer.Exit(_run_terminal(list(ctx.args)))


@app.command()
def serve() -> None:
    """Run the HTTP/SSE server."""
    from agents.interfaces.server.__main__ import main as server_main

    server_main()


@app.command("bridge", context_settings=CONTEXT)
def bridge_command(ctx: typer.Context) -> None:
    """Run the internal terminal bridge."""
    from agents.interfaces.bridge.ndjson import main as bridge_main

    bridge_main(list(ctx.args))


def main() -> None:
    app()


def _run_terminal(args: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
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
        typer.echo("bun is required for the terminal app. Install bun or run make bridge-fallback.", err=True)
        return 127


def _merge_pythonpath(first: str, existing: str) -> str:
    return first if not existing else os.pathsep.join([first, existing])


if __name__ == "__main__":
    main()
