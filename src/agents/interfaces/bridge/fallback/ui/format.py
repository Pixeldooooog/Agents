from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def estimate_session_tokens(session) -> str:
    try:
        return str(session._estimate_tokens(getattr(session, "messages", [])))
    except Exception:
        return "unknown"


def compact(value) -> str:
    text = str(value)
    return text if len(text) <= 220 else text[:217] + "..."


def tool_arguments(arguments: Any | None) -> str:
    if not arguments:
        return ""
    try:
        text = json.dumps(arguments, ensure_ascii=False)
    except TypeError:
        text = str(arguments)
    return compact(text)


def short_path(path: str) -> str:
    try:
        value = Path(path).expanduser()
        home = Path.home()
        return "~/%s" % value.relative_to(home) if value.is_relative_to(home) else str(value)
    except Exception:
        return str(path)


def model_base_url(session) -> str:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    config = getattr(model_client, "config", None)
    return str(getattr(config, "base_url", "") or "")


def model_endpoint(session) -> str:
    base_url = model_base_url(session)
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    return parsed.netloc or base_url


def short_endpoint(endpoint: str, limit: int = 36) -> str:
    value = str(endpoint or "")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def path_writable(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".agents-terminal-write-check"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def model_label(profile: str, protocol: str, model: str) -> str:
    base = "%s · %s" % (protocol, model)
    if not profile or profile in {protocol, model}:
        return base
    return "%s · %s" % (profile, base)
