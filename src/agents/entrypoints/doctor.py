from __future__ import annotations

import json
import shutil
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from agents.kernel.config.paths import ENV_FILE
from agents.kernel.config.profiles import ModelProfile, build_model_profiles


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


CommandLookup = Callable[[str], str | None]
TcpConnect = Callable[[str, int, float], bool]


def run_doctor(
    *,
    repo_root: Path | None = None,
    settings=None,
    model_profiles: Iterable[ModelProfile] | None = None,
    command_lookup: CommandLookup = shutil.which,
    tcp_connect: TcpConnect | None = None,
    env_file: Path | None = None,
) -> list[DoctorCheck]:
    root = repo_root or Path(__file__).resolve().parents[3]
    runtime_settings = settings or _load_settings()
    profiles = list(model_profiles) if model_profiles is not None else build_model_profiles(runtime_settings)
    env_path = Path(env_file or ENV_FILE)
    checks = [
        _python_check(),
        _env_check(env_path),
        _model_check(profiles),
        _proxy_check(runtime_settings, tcp_connect or _tcp_connect),
        _server_check(runtime_settings),
        _workspace_check(runtime_settings, root),
        _sandbox_check(runtime_settings, command_lookup),
        _database_check(runtime_settings, root),
        _web_search_check(runtime_settings),
        _terminal_check(root, command_lookup),
        _web_check(root, command_lookup),
    ]
    return checks


def main(*, json_output: bool = False) -> int:
    checks = run_doctor()
    if json_output:
        print(json.dumps([check.to_dict() for check in checks], ensure_ascii=False, indent=2))
    else:
        _print_checks(checks)
    return 1 if any(check.status == "fail" for check in checks) else 0


def _load_settings():
    from agents.interfaces.server.core.config import settings

    return settings


def _python_check() -> DoctorCheck:
    version = "%s.%s.%s" % sys.version_info[:3]
    if sys.version_info < (3, 10):
        return DoctorCheck("python", "fail", "Python %s; requires 3.10+" % version)
    return DoctorCheck("python", "ready", "Python %s" % version)


def _env_check(env_path: Path) -> DoctorCheck:
    if env_path.is_file():
        return DoctorCheck("env", "ready", str(env_path))
    return DoctorCheck("env", "warn", "%s missing; copy .env.example when using real models" % env_path)


def _model_check(profiles: list[ModelProfile]) -> DoctorCheck:
    if not profiles:
        return DoctorCheck("models", "fail", "no configured model profiles; set one API key + model in .env")
    summary = ", ".join(
        "%s=%s/%s@%s" % (profile.name, profile.protocol, profile.model, profile.endpoint or "default")
        for profile in profiles[:6]
    )
    if len(profiles) > 6:
        summary += ", +%d more" % (len(profiles) - 6)
    return DoctorCheck("models", "ready", summary)


def _proxy_check(settings, tcp_connect: TcpConnect) -> DoctorCheck:
    name, value = _configured_proxy(settings)
    if not value:
        return DoctorCheck("proxy", "ready", "project proxy not configured; transport can use shell proxy env")

    parsed = urlparse(value)
    host = parsed.hostname or ""
    port = parsed.port or _default_proxy_port(parsed.scheme)
    display = "%s:%s" % (host or "unknown", port or "unknown")
    if not host or port is None:
        return DoctorCheck("proxy", "fail", "%s is invalid; set a URL such as http://127.0.0.1:7890" % name)
    if _is_localhost(host) and not tcp_connect(host, port, 0.25):
        return DoctorCheck(
            "proxy",
            "fail",
            "%s %s is not listening; project proxy overrides shell proxy env for model requests" % (name, display),
        )
    return DoctorCheck("proxy", "ready", "%s %s" % (name, display))


def _configured_proxy(settings) -> tuple[str, str]:
    agent = getattr(settings, "agent", None)
    for name in ("HTTPS_PROXY", "ALL_PROXY", "HTTP_PROXY"):
        value = str(getattr(agent, name, "") or "").strip()
        if value:
            return "AGENT_%s" % name, value
    return "", ""


def _default_proxy_port(scheme: str) -> int | None:
    if scheme in {"http", "socks5", "socks4"}:
        return 80 if scheme == "http" else 1080
    if scheme == "https":
        return 443
    return None


def _is_localhost(host: str) -> bool:
    return host.lower() in {"localhost", "127.0.0.1", "::1"}


def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _server_check(settings) -> DoctorCheck:
    server = settings.server
    return DoctorCheck(
        "server",
        "ready",
        "%s:%s%s" % (getattr(server, "HOST", "0.0.0.0"), getattr(server, "PORT", ""), getattr(server, "API_PREFIX", "")),
    )


def _workspace_check(settings, root: Path) -> DoctorCheck:
    configured = Path(str(getattr(settings.agent, "WORKSPACE_ROOT", ".agents/workspaces")))
    path = configured if configured.is_absolute() else root / configured
    return DoctorCheck("workspace", "ready", str(path))


def _sandbox_check(settings, command_lookup: CommandLookup) -> DoctorCheck:
    provider = str(getattr(settings.agent, "SANDBOX_PROVIDER", "local") or "local")
    profile = str(getattr(settings.agent, "SANDBOX_PROFILE", "restricted") or "restricted")
    if provider == "docker" and not command_lookup("docker"):
        return DoctorCheck("sandbox", "fail", "docker profile selected but docker is not on PATH")
    if provider not in {"local", "docker"}:
        return DoctorCheck("sandbox", "fail", "unknown provider %s" % provider)
    return DoctorCheck("sandbox", "ready", "%s/%s" % (provider, profile))


def _database_check(settings, root: Path) -> DoctorCheck:
    store = str(getattr(settings.agent, "RUN_STORE", "memory") or "memory")
    configured = Path(str(getattr(settings.agent, "DB_PATH", ".agents/agents.db") or ".agents/agents.db"))
    path = configured if configured.is_absolute() else root / configured
    if store == "sqlite":
        return DoctorCheck("database", "ready", "sqlite %s" % path)
    return DoctorCheck("database", "ready", "%s run store; sqlite path %s" % (store, path))


def _web_search_check(settings) -> DoctorCheck:
    web_search = getattr(settings, "web_search", None)
    provider = str(getattr(web_search, "PROVIDER", "none") or "none")
    if provider == "none":
        return DoctorCheck("web_search", "warn", "disabled")
    if provider == "tavily" and not str(getattr(web_search, "TAVILY_API_KEY", "") or "").strip():
        return DoctorCheck("web_search", "fail", "Tavily selected but WEB_SEARCH_TAVILY_API_KEY is empty")
    return DoctorCheck("web_search", "ready", provider)


def _terminal_check(root: Path, command_lookup: CommandLookup) -> DoctorCheck:
    if not (root / "apps" / "terminal" / "package.json").is_file():
        return DoctorCheck("terminal", "fail", "apps/terminal/package.json missing")
    if not command_lookup("bun"):
        return DoctorCheck("terminal", "warn", "bun missing; terminal UI cannot start")
    return DoctorCheck("terminal", "ready", "bun available")


def _web_check(root: Path, command_lookup: CommandLookup) -> DoctorCheck:
    web_root = root / "apps" / "web"
    if not (web_root / "package.json").is_file():
        return DoctorCheck("web", "fail", "apps/web/package.json missing")
    if not command_lookup("npm"):
        return DoctorCheck("web", "warn", "npm missing; web UI cannot build")
    if not (web_root / "dist" / "index.html").is_file():
        return DoctorCheck("web", "warn", "npm available; run npm run build to create dist")
    return DoctorCheck("web", "ready", "dist build present")


def _print_checks(checks: Iterable[DoctorCheck]) -> None:
    for check in checks:
        marker = {"ready": "ok", "warn": "warn", "fail": "fail"}.get(check.status, check.status)
        print("%-5s %-12s %s" % (marker, check.name, check.detail))


if __name__ == "__main__":
    raise SystemExit(main())
