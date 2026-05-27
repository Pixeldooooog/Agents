from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"
SUPPORTED_TRANSPORTS = ("stdio", "sse", "sse-ide", "http", "ws", "ws-ide", "sdk", "claudeai-proxy")


def mcp_settings(context: ToolRuntimeContext) -> Any:
    settings = getattr(context, "settings", None)
    if settings is None:
        settings = SimpleNamespace()
        context.settings = settings
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        mcp = SimpleNamespace()
        settings.mcp = mcp
    for name, value in _MCP_SETTING_DEFAULTS.items():
        if not hasattr(mcp, name):
            setattr(mcp, name, _default_value(value))
    return mcp


def root_settings(context: ToolRuntimeContext) -> Any:
    mcp_settings(context)
    return context.settings


def configured_server_payload(settings: Any) -> dict[str, Any]:
    configured_command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
    configured_url = str(getattr(settings, "SERVER_URL", "") or "").strip()
    return {
        "name": str(getattr(settings, "SERVER_NAME", "") or "").strip(),
        "command": configured_command,
        "transport": str(getattr(settings, "SERVER_TRANSPORT", "") or "stdio"),
        "url": configured_url,
        "headers": headers(settings),
        "execution_mode": str(getattr(settings, "EXECUTION_MODE", "") or ""),
        "sandbox_profile": str(getattr(settings, "SANDBOX_PROFILE", "") or ""),
        "auth_required": bool(getattr(settings, "AUTH_REQUIRED", False)),
        "auth_url": str(getattr(settings, "AUTH_URL", "") or ""),
        "auth_status": str(getattr(settings, "AUTH_STATUS", "") or ""),
        "auth_message": str(getattr(settings, "AUTH_MESSAGE", "") or ""),
        "enabled": bool(configured_command or configured_url),
    }


def apply_record_to_settings(settings: Any, record: Any) -> None:
    settings.SERVER_NAME = record.name
    settings.SERVER_COMMAND = record.command
    settings.SERVER_TRANSPORT = record.transport
    settings.SERVER_URL = record.url
    settings.SERVER_HEADERS = dict(record.headers)
    settings.SERVER_HEADERS_JSON = _headers_json(settings.SERVER_HEADERS)
    settings.EXECUTION_MODE = record.execution_mode
    settings.SANDBOX_PROFILE = record.sandbox_profile
    settings.AUTH_REQUIRED = record.auth_required
    settings.AUTH_URL = record.auth_url
    settings.AUTH_STATUS = record.auth_status
    settings.AUTH_MESSAGE = record.auth_message


def clear_configured_server(settings: Any) -> None:
    settings.SERVER_NAME = ""
    settings.SERVER_COMMAND = ""
    settings.SERVER_URL = ""
    settings.SERVER_HEADERS = {}
    settings.SERVER_HEADERS_JSON = ""
    settings.AUTH_REQUIRED = False
    settings.AUTH_URL = ""
    settings.AUTH_STATUS = ""
    settings.AUTH_MESSAGE = ""


def set_headers(settings: Any, value: dict[str, str]) -> None:
    settings.SERVER_HEADERS = dict(value)
    settings.SERVER_HEADERS_JSON = _headers_json(settings.SERVER_HEADERS)


def transport(value: str) -> str:
    selected = str(value or "stdio").strip() or "stdio"
    if selected not in SUPPORTED_TRANSPORTS:
        raise ValueError("unsupported MCP transport: %s" % selected)
    return selected


def headers(settings: Any) -> dict[str, str]:
    raw = getattr(settings, "SERVER_HEADERS", None)
    if isinstance(raw, dict):
        return coerce_headers(raw)
    raw_json = str(getattr(settings, "SERVER_HEADERS_JSON", "") or "").strip()
    if not raw_json:
        return {}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return coerce_headers(parsed) if isinstance(parsed, dict) else {}


def coerce_headers(value: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def headers_with_ide_auth(headers_value: dict[str, str], *, transport_value: str, auth_token: str) -> dict[str, str]:
    if transport_value != "ws-ide":
        return headers_value
    token = str(auth_token or "").strip()
    if not token or has_header(headers_value, IDE_AUTH_HEADER):
        return headers_value
    return {**headers_value, IDE_AUTH_HEADER: token}


def has_header(headers_value: dict[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(str(key).lower() == wanted for key in headers_value)


def _headers_json(headers_value: dict[str, str]) -> str:
    return json.dumps(headers_value, ensure_ascii=False, sort_keys=True) if headers_value else ""


def _default_value(value: Any) -> Any:
    return dict(value) if isinstance(value, dict) else value


_MCP_SETTING_DEFAULTS = {
    "SERVER_NAME": "",
    "SERVER_COMMAND": "",
    "SERVER_TRANSPORT": "stdio",
    "SERVER_URL": "",
    "SERVER_HEADERS": {},
    "SERVER_HEADERS_JSON": "",
    "EXECUTION_MODE": "",
    "SANDBOX_PROFILE": "",
    "AUTH_REQUIRED": False,
    "AUTH_URL": "",
    "AUTH_STATUS": "",
    "AUTH_MESSAGE": "",
}
