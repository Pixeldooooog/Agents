from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolExecutionError
from agents.kernel.config import AgentConfigError, resolve_model_client_config
from agents.kernel.governance import build_tool_permission_policy
from agents.kernel.models import ModelClient
from agents.kernel.session_state import save_session_state
from agents.kernel.specs import AgentSpec


CONFIG_VALUE_UNSET = object()

CONFIG_MANAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "setting": {
            "type": "string",
            "description": 'The setting key, for example "theme", "model", or "permissions.defaultMode".',
        },
        "value": {
            "type": ["string", "boolean", "number"],
            "description": "The new value. Omit this field to get the current value.",
        },
    },
    "required": ["setting"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ConfigSetting:
    value_type: str
    description: str
    default: Any = None
    options: tuple[str, ...] = ()


SUPPORTED_CONFIG_SETTINGS: dict[str, ConfigSetting] = {
    "theme": ConfigSetting(
        "string",
        "Color theme for the UI",
        default="dark",
        options=("auto", "dark", "light", "light-daltonized", "dark-daltonized", "light-ansi", "dark-ansi"),
    ),
    "editorMode": ConfigSetting("string", "Key binding mode", default="normal", options=("normal", "vim")),
    "verbose": ConfigSetting("boolean", "Show detailed debug output", default=False),
    "preferredNotifChannel": ConfigSetting(
        "string",
        "Preferred notification channel",
        default="auto",
        options=("auto", "iterm2", "iterm2_with_bell", "terminal_bell", "kitty", "ghostty", "notifications_disabled"),
    ),
    "autoCompactEnabled": ConfigSetting("boolean", "Auto-compact when context is full", default=True),
    "autoMemoryEnabled": ConfigSetting("boolean", "Enable auto-memory", default=False),
    "autoDreamEnabled": ConfigSetting("boolean", "Enable background memory consolidation", default=False),
    "fileCheckpointingEnabled": ConfigSetting("boolean", "Enable file checkpointing for code rewind", default=True),
    "showTurnDuration": ConfigSetting("boolean", "Show turn duration message after responses", default=True),
    "terminalProgressBarEnabled": ConfigSetting("boolean", "Show OSC progress indicator in supported terminals", default=True),
    "todoFeatureEnabled": ConfigSetting("boolean", "Enable todo/task tracking", default=True),
    "model": ConfigSetting("string", "Override the default model", default="default"),
    "alwaysThinkingEnabled": ConfigSetting("boolean", "Enable extended thinking", default=False),
    "permissions.defaultMode": ConfigSetting(
        "string",
        "Default permission mode for tool usage",
        default="default",
        options=("default", "plan", "acceptEdits", "dontAsk", "auto"),
    ),
    "language": ConfigSetting("string", "Preferred language for model responses", default=""),
    "teammateMode": ConfigSetting(
        "string",
        "How to spawn teammates",
        default="auto",
        options=("auto", "tmux", "in-process"),
    ),
    "classifierPermissionsEnabled": ConfigSetting("boolean", "Enable classifier-backed permission rules", default=False),
    "voiceEnabled": ConfigSetting("boolean", "Enable voice dictation", default=False),
    "remoteControlAtStartup": ConfigSetting("boolean", "Enable Remote Control for all sessions", default=False),
    "taskCompleteNotifEnabled": ConfigSetting("boolean", "Notify when an agent finishes while idle", default=False),
    "inputNeededNotifEnabled": ConfigSetting("boolean", "Notify when input or permission is needed", default=False),
    "agentPushNotifEnabled": ConfigSetting("boolean", "Allow agent-initiated push notifications", default=False),
}

_PERMISSION_MODE_FOR_CONFIG = {
    "default": "auto",
    "auto": "auto",
    "plan": "ask",
    "acceptEdits": "auto",
    "dontAsk": "auto",
}


async def config_manage(
    context: ToolRuntimeContext,
    setting: str,
    value: Any = CONFIG_VALUE_UNSET,
) -> dict[str, Any]:
    key = _required_setting(setting)
    config = SUPPORTED_CONFIG_SETTINGS.get(key)
    if config is None:
        _raise_config_error('Unknown setting: "%s"' % key)

    if value is CONFIG_VALUE_UNSET:
        return {"success": True, "operation": "get", "setting": key, "value": _current_value(context, key, config)}

    if key == "remoteControlAtStartup" and isinstance(value, str) and value.strip().lower() == "default":
        previous = _current_value(context, key, config)
        _delete_override(context, key)
        await save_session_state(context)
        return {"success": True, "operation": "set", "setting": key, "previousValue": previous, "newValue": "default"}

    final_value = _coerce_value(key, config, value)
    previous = _current_value(context, key, config)
    try:
        await _apply_config_value(context, key, final_value)
    except AgentConfigError as exc:
        _raise_config_error(str(exc), operation="set", setting=key)
    except Exception as exc:  # noqa: BLE001 - config errors are model-visible.
        _raise_config_error(str(exc), operation="set", setting=key)
    return {"success": True, "operation": "set", "setting": key, "previousValue": previous, "newValue": final_value}


def format_config_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    if payload.get("success"):
        setting = str(payload.get("setting") or "")
        if payload.get("operation") == "get":
            return "%s = %s" % (setting, _json_string(payload.get("value")))
        return "Set %s to %s" % (setting, _json_string(payload.get("newValue")))
    return "Error: %s" % str(payload.get("error") or "configuration update failed")


async def _apply_config_value(context: ToolRuntimeContext, setting: str, value: Any) -> None:
    if setting == "model":
        await _apply_model(context, value)
    elif setting == "permissions.defaultMode":
        await _apply_permission_mode(context, value)
    else:
        _set_override(context, setting, value)
        await save_session_state(context)


async def _apply_model(context: ToolRuntimeContext, value: Any) -> None:
    model = str(value or "").strip()
    if not model:
        raise ValueError("model is required")
    spec = _agent_spec(context)
    if model.lower() == "default":
        updated = replace(spec, model=replace(spec.model, model=None))
        _delete_override(context, "model")
    else:
        updated = replace(spec, model=replace(spec.model, model=model))
        _set_override(context, "model", model)
    context.agent_spec = updated

    runtime = _runtime(context)
    if runtime is not None:
        settings = getattr(context, "settings", None)
        if settings is not None:
            config = resolve_model_client_config(
                settings,
                protocol=updated.model.protocol,
                model=updated.model.model,
                base_url=updated.model.base_url,
                api_key=updated.model.api_key,
            )
            old_client = getattr(runtime, "model_client", None)
            runtime.model_client = ModelClient(config)
            runner = getattr(runtime, "model_turn_runner", None)
            if runner is not None:
                runner.model_client = runtime.model_client
            _replace_runtime_config(runtime, protocol=config.protocol, model=config.model)
            close = getattr(old_client, "async_close", None)
            if close is not None and old_client is not runtime.model_client:
                await close()
        else:
            _replace_runtime_config(runtime, model=model)
    await save_session_state(context)


async def _apply_permission_mode(context: ToolRuntimeContext, value: Any) -> None:
    mode = str(value or "").strip()
    local_mode = _PERMISSION_MODE_FOR_CONFIG.get(mode)
    if local_mode is None:
        raise ValueError('Invalid value "%s". Options: %s' % (value, ", ".join(SUPPORTED_CONFIG_SETTINGS["permissions.defaultMode"].options)))
    spec = _agent_spec(context)
    updated = replace(
        spec,
        permission_profile=mode,
        tool_permissions=replace(spec.tool_permissions, mode=local_mode),
    )
    context.agent_spec = updated
    context.permission_overridden = True
    context.permission_profile_override = mode
    context.permission_mode_override = local_mode
    context.permission_restrict_allowed_tools = updated.tool_permissions.allowed_tools is not None
    context.permission_allowed_tools_override = list(updated.tool_permissions.allowed_tools or [])
    context.permission_denied_tools_override = list(updated.tool_permissions.denied_tools)
    context.approval_required_tools_override = list(updated.tool_permissions.approval_required_tools)
    _set_override(context, "permissions.defaultMode", mode)
    runtime = _runtime(context)
    orchestrator = getattr(runtime, "tool_orchestrator", None) if runtime is not None else None
    if orchestrator is not None:
        orchestrator.permission_policy = build_tool_permission_policy(updated)
    await save_session_state(context)


def _coerce_value(setting: str, config: ConfigSetting, value: Any) -> Any:
    if config.value_type == "boolean":
        final = value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                final = True
            elif lowered == "false":
                final = False
        if not isinstance(final, bool):
            _raise_config_error("%s requires true or false." % setting, operation="set", setting=setting)
        return final
    final = str(value)
    if config.options and final not in config.options:
        _raise_config_error('Invalid value "%s". Options: %s' % (value, ", ".join(config.options)), operation="set", setting=setting)
    return final


def _current_value(context: ToolRuntimeContext, setting: str, config: ConfigSetting) -> Any:
    override = _override_value(context, setting)
    if override is not CONFIG_VALUE_UNSET:
        return override
    if setting == "model":
        return _current_model(context)
    if setting == "permissions.defaultMode":
        return _current_permission_mode(context)
    return config.default


def _current_model(context: ToolRuntimeContext) -> str:
    runtime = _runtime(context)
    runtime_model = str(getattr(runtime, "model", "") or "").strip() if runtime is not None else ""
    if runtime_model:
        return runtime_model
    spec = _agent_spec(context)
    if spec.model.model:
        return spec.model.model
    configured = _configured_model(context)
    return configured or "default"


def _current_permission_mode(context: ToolRuntimeContext) -> str:
    profile = str(getattr(context, "permission_profile_override", "") or "").strip()
    if profile in SUPPORTED_CONFIG_SETTINGS["permissions.defaultMode"].options:
        return profile
    spec = _agent_spec(context)
    if spec.permission_profile in SUPPORTED_CONFIG_SETTINGS["permissions.defaultMode"].options:
        return spec.permission_profile
    mode = spec.tool_permissions.normalized_mode()
    if mode == "ask":
        return "plan"
    return "default"


def _configured_model(context: ToolRuntimeContext) -> str:
    settings = getattr(context, "settings", None)
    if settings is None:
        return ""
    protocol = str(getattr(getattr(settings, "agent", None), "PROTOCOL", "") or "openai-chat").strip()
    models = getattr(settings, "models", None)
    agent = getattr(settings, "agent", None)
    if protocol == "claude-messages":
        return str(getattr(agent, "CLAUDE_MODEL", "") or getattr(getattr(models, "anthropic", None), "MODEL", "") or "").strip()
    if protocol == "gemini":
        return str(getattr(getattr(models, "gemini", None), "MODEL", "") or "").strip()
    if protocol == "openai-responses":
        return str(getattr(getattr(models, "openai_responses", None), "MODEL", "") or getattr(getattr(models, "openai", None), "MODEL", "") or "").strip()
    return str(getattr(getattr(models, "openai", None), "MODEL", "") or "").strip()


def _required_setting(value: Any) -> str:
    setting = str(value or "").strip()
    if not setting:
        _raise_config_error("setting is required")
    return setting


def _agent_spec(context: ToolRuntimeContext) -> AgentSpec:
    spec = getattr(context, "agent_spec", None)
    if isinstance(spec, AgentSpec):
        return spec
    workspace = context.workspace
    return AgentSpec.from_overrides(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        workspace_path=str(workspace.path),
        enabled_tools=list(getattr(context, "enabled_tools", []) or []),
    )


def _runtime(context: ToolRuntimeContext) -> Any | None:
    session = getattr(context, "session", None)
    return getattr(session, "runtime", None)


def _replace_runtime_config(runtime: Any, **updates: Any) -> None:
    config = getattr(runtime, "config", None)
    if config is None:
        return
    runtime.config = replace(config, **{key: value for key, value in updates.items() if value is not None})


def _set_override(context: ToolRuntimeContext, setting: str, value: Any) -> None:
    context.config_overrides["config.%s" % setting] = _json_string(value)


def _delete_override(context: ToolRuntimeContext, setting: str) -> None:
    context.config_overrides.pop("config.%s" % setting, None)


def _override_value(context: ToolRuntimeContext, setting: str) -> Any:
    raw = context.config_overrides.get("config.%s" % setting)
    if raw is None:
        return CONFIG_VALUE_UNSET
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _raise_config_error(error: str, *, operation: str | None = None, setting: str | None = None) -> None:
    payload: dict[str, Any] = {"success": False, "error": error}
    if operation is not None:
        payload["operation"] = operation
    if setting is not None:
        payload["setting"] = setting
    raise ToolExecutionError("Error: %s" % error, raw=payload)
