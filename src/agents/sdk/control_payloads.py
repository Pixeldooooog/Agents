from __future__ import annotations

import uuid
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from agents.kernel.governance.factory import build_tool_permission_policy
from agents.kernel.mcp.config import MCPServerRecord
from agents.kernel.schema import ToolCall
from agents.kernel.tasks import TaskRecord
from agents.platform.commands import COMMANDS, command_names
from agents.sdk.control import SDKControlInitializeRequest, SDKControlPermissionRequest
from agents.sdk.event_projection import _json_list, _text_field
from agents.sdk.file_rewind import _record_cwd
from agents.sdk.options import _spec_from_options
from agents.sdk.types import SDKOptions, SDKSystemMessage

IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"


try:
    _SDK_VERSION = version("agents")
except PackageNotFoundError:
    _SDK_VERSION = "0.1.0"


def _initialize_control_response_payload(
    settings: Any,
    options: SDKOptions,
    request: SDKControlInitializeRequest,
) -> dict[str, Any]:
    model = options.model or _default_model_from_settings(settings)
    return {
        "commands": _slash_command_infos(),
        "agents": _agent_infos_from_request(request),
        "output_style": str(options.metadata.get("output_style") or options.metadata.get("outputStyle") or "default"),
        "available_output_styles": ["default"],
        "models": _model_infos(model),
        "account": _account_info_from_options(options),
        "fast_mode_state": options.metadata.get("fast_mode_state", options.metadata.get("fastModeState")),
    }


async def _permission_control_response_payload(
    request: SDKControlPermissionRequest,
    options: SDKOptions,
) -> dict[str, Any]:
    policy = build_tool_permission_policy(_spec_from_options(options))
    decision = await policy.authorize(
        ToolCall(
            id=request.tool_use_id,
            name=request.tool_name,
            arguments=dict(request.input or {}),
        )
    )
    if decision.requires_approval:
        behavior = "ask"
    elif decision.allowed:
        behavior = "allow"
    else:
        behavior = "deny"
    return {
        "behavior": behavior,
        "allowed": decision.allowed,
        "requires_approval": decision.requires_approval,
        "reason": decision.reason,
        "metadata": decision.metadata,
    }


def _settings_control_response_payload(options: SDKOptions) -> dict[str, Any]:
    effective = {
        "model": options.model,
        "permissionMode": options.permission_mode,
        "systemPrompt": options.system_prompt,
        "cwd": options.cwd,
        "allowedTools": list(options.allowed_tools or []),
        "skills": list(options.skills or []),
    }
    return {
        "effective": {key: value for key, value in effective.items() if value not in (None, "", [])},
        "sources": [{"source": "flagSettings", "settings": dict(options.metadata.get("flagSettings") or {})}],
        "applied": {"model": options.model or "", "effort": None},
    }


def _empty_context_usage_payload(options: SDKOptions) -> dict[str, Any]:
    return {
        "categories": [],
        "totalTokens": 0,
        "maxTokens": 0,
        "rawMaxTokens": 0,
        "percentage": 0,
        "gridRows": [],
        "model": options.model or "",
        "memoryFiles": [],
        "mcpTools": [],
        "isAutoCompactEnabled": False,
        "agents": [],
        "apiUsage": None,
    }


def _slash_command_infos() -> list[dict[str, str]]:
    return [
        {
            "name": command.name.lstrip("/"),
            "description": command.action,
            "argumentHint": command.argument_hint,
        }
        for command in COMMANDS
    ]


def _mcp_record_from_control_config(
    name: str,
    config: dict[str, Any],
    *,
    tenant_id: str,
    user_id: str,
    agent_id: str,
    workspace_id: str,
) -> MCPServerRecord:
    transport = str(config.get("type") or "stdio")
    args = config.get("args") if isinstance(config.get("args"), list) else []
    command_parts = [str(config.get("command") or ""), *[str(arg) for arg in args]]
    command = " ".join(part for part in command_parts if part).strip()
    headers = _mcp_headers_from_control_config(config, transport=transport)
    return MCPServerRecord(
        name=name,
        command=command,
        transport=transport,
        url=str(config.get("url") or ""),
        headers=headers,
        enabled=True,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
        workspace_id=workspace_id,
    )


def _task_in_sdk_scope(task: TaskRecord, options: SDKOptions) -> bool:
    return (
        task.tenant_id == (options.tenant_id or "")
        and task.user_id in ("", options.user_id or "")
        and task.agent_id in ("", options.agent_id or "")
    )


def _task_id_matches(task_id: str, target: str) -> bool:
    return task_id == target or task_id.replace("task_", "", 1).startswith(target)


def _sdk_task_payload(task: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "short_id": task.task_id.replace("task_", "", 1)[:12],
        "title": task.title,
        "input": task.input,
        "status": task.status.value,
        "agent_id": task.agent_id,
        "workspace_id": task.workspace_id,
        "metadata": dict(task.metadata),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _sdk_system_message(
    *,
    session_id: str,
    run_id: str,
    cwd: str,
    model: str,
    tools: list[str],
    skills: list[str],
    permission_mode: str | None,
    metadata: dict[str, Any],
    mcp_servers: list[dict[str, str]],
) -> SDKSystemMessage:
    return SDKSystemMessage(
        session_id=session_id,
        run_id=run_id,
        agents=_metadata_string_list(metadata, "agents", "sdk_agents"),
        apiKeySource=_api_key_source(metadata.get("apiKeySource", metadata.get("api_key_source"))),
        betas=_metadata_string_list(metadata, "betas", "sdk_betas"),
        claude_code_version=_text_field(metadata, "claude_code_version", "sdk_version") or _SDK_VERSION,
        cwd=cwd,
        tools=tools,
        mcp_servers=mcp_servers,
        model=model,
        permissionMode=_permission_mode(metadata.get("permissionMode", permission_mode)),
        slash_commands=_metadata_string_list(metadata, "slash_commands", "slashCommands") or command_names(),
        output_style=_text_field(metadata, "output_style", "outputStyle") or "default",
        skills=_metadata_string_list(metadata, "skills", "sdk_skills") or skills,
        plugins=_plugin_list_field(metadata.get("plugins", metadata.get("sdk_plugins"))),
        fast_mode_state=_fast_mode_state(metadata.get("fast_mode_state", metadata.get("fastModeState"))),
        uuid=_text_field(metadata, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
    )


def _metadata_string_list(metadata: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "")]
        if isinstance(value, str) and value:
            parsed = _json_list(value)
            if parsed:
                return [str(item) for item in parsed if str(item or "")]
    return []


def _settings_mcp_server_statuses(settings: Any) -> list[dict[str, str]]:
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        return []
    name = str(getattr(mcp, "SERVER_NAME", "") or "default")
    transport = str(getattr(mcp, "SERVER_TRANSPORT", "stdio") or "stdio")
    command = str(getattr(mcp, "SERVER_COMMAND", "") or "").strip()
    url = str(getattr(mcp, "SERVER_URL", "") or "").strip()
    auth_required = bool(getattr(mcp, "AUTH_REQUIRED", False))
    if transport == "stdio" and not command and not auth_required:
        return []
    if transport != "stdio" and not url and not auth_required:
        return []
    return [{"name": name, "status": _mcp_status(enabled=True, auth_required=auth_required, auth_status=getattr(mcp, "AUTH_STATUS", ""))}]


def _mcp_server_status_from_record(record: MCPServerRecord) -> dict[str, str]:
    return {
        "name": record.name,
        "status": _mcp_status(
            enabled=record.enabled,
            auth_required=record.auth_required,
            auth_status=record.auth_status,
        ),
    }


def _merge_mcp_server_statuses(
    base: list[dict[str, str]],
    extra: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for item in [*base, *extra]:
        name = str(item.get("name") or "")
        if name:
            merged[name] = {"name": name, "status": str(item.get("status") or "connected")}
    return sorted(merged.values(), key=lambda item: item["name"])


def _agent_infos_from_request(request: SDKControlInitializeRequest) -> list[dict[str, str]]:
    agents = request.agents or {}
    infos: list[dict[str, str]] = []
    for name, definition in agents.items():
        payload = definition if isinstance(definition, dict) else {}
        info = {
            "name": str(name),
            "description": str(payload.get("description") or payload.get("prompt") or ""),
        }
        model = str(payload.get("model") or "")
        if model:
            info["model"] = model
        infos.append(info)
    return infos


def _model_infos(model: str) -> list[dict[str, Any]]:
    value = model or "default"
    return [{"value": value, "displayName": value, "description": "Configured SDK model"}]


def _account_info_from_options(options: SDKOptions) -> dict[str, str]:
    source = _api_key_source(options.metadata.get("apiKeySource", options.metadata.get("api_key_source")))
    return {"apiKeySource": source}


def _default_model_from_settings(settings: Any) -> str:
    agent_model = str(getattr(getattr(settings, "agent", None), "CLAUDE_MODEL", "") or "")
    if agent_model:
        return agent_model
    models = getattr(settings, "models", None)
    for name in ("anthropic", "openai", "openai_responses", "gemini"):
        value = str(getattr(getattr(models, name, None), "MODEL", "") or "")
        if value:
            return value
    return ""


def _mcp_headers_from_control_config(config: dict[str, Any], *, transport: str) -> dict[str, str]:
    raw_headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    headers = {str(key): str(value) for key, value in raw_headers.items()}
    token = str(config.get("authToken") or config.get("auth_token") or "").strip()
    if transport == "ws-ide" and token and not _has_header(headers, IDE_AUTH_HEADER):
        headers[IDE_AUTH_HEADER] = token
    return headers


def _has_header(headers: dict[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(str(key).lower() == wanted for key in headers)


def _api_key_source(value: Any) -> Literal["user", "project", "org", "temporary", "oauth"]:
    text = str(value or "")
    if text in {"user", "project", "org", "temporary", "oauth"}:
        return text
    return "project"


def _permission_mode(value: Any) -> Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]:
    text = str(value or "")
    if text in {"default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"}:
        return text
    normalized = text.strip().lower().replace("_", "-")
    if normalized in {"accept-edits", "acceptedits"}:
        return "acceptEdits"
    if normalized in {"bypass", "bypass-permissions", "bypasspermissions"}:
        return "bypassPermissions"
    if normalized in {"deny", "dont-ask", "dontask"}:
        return "dontAsk"
    if normalized == "plan":
        return "plan"
    return "default"


def _fast_mode_state(value: Any) -> Literal["off", "cooldown", "on"] | None:
    text = str(value or "")
    if text in {"off", "cooldown", "on"}:
        return text
    return None


def _plugin_list_field(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    plugins: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            if item:
                plugins.append({"name": item, "path": ""})
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        plugin = {"name": name, "path": str(item.get("path") or "")}
        source = str(item.get("source") or "")
        if source:
            plugin["source"] = source
        plugins.append(plugin)
    return plugins


def _mcp_status(*, enabled: bool, auth_required: bool, auth_status: Any) -> str:
    if not enabled:
        return "disabled"
    status = str(auth_status or "").strip().lower()
    if auth_required and status not in {"authenticated", "connected", "ok", "ready"}:
        return "needs-auth"
    if status in {"failed", "error"}:
        return "failed"
    if status == "pending":
        return "pending"
    return "connected"
