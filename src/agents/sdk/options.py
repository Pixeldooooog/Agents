from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.kernel.specs import AgentSpec
from agents.sdk.control import (
    SDKControlApplyFlagSettingsRequest,
    SDKControlRequestInner,
    SDKControlSetModelRequest,
    SDKControlSetPermissionModeRequest,
)
from agents.sdk.types import (
    SDKForkSessionOptions,
    SDKGetSessionMessagesOptions,
    SDKListSessionsOptions,
    SDKOptions,
)


def _coerce_options(options: SDKOptions | dict[str, Any] | None) -> SDKOptions:
    if options is None:
        return SDKOptions()
    if isinstance(options, SDKOptions):
        return options
    return SDKOptions.model_validate(options)


def _merge_session_options(
    base: SDKOptions,
    override: SDKOptions | dict[str, Any] | None,
    *,
    session_id: str,
) -> SDKOptions:
    values = base.model_dump()
    if override is not None:
        override_options = _coerce_options(override)
        for key in override_options.model_fields_set:
            if key == "metadata":
                values["metadata"] = {
                    **values.get("metadata", {}),
                    **override_options.metadata,
                }
            else:
                values[key] = getattr(override_options, key)
    values["session_id"] = session_id
    return SDKOptions.model_validate(values)


def _apply_session_control_request(options: SDKOptions, request: SDKControlRequestInner) -> SDKOptions:
    if isinstance(request, SDKControlSetModelRequest):
        return options.model_copy(update={"model": request.model})
    if isinstance(request, SDKControlSetPermissionModeRequest):
        return options.model_copy(update={"permission_mode": request.mode})
    if isinstance(request, SDKControlApplyFlagSettingsRequest):
        return _apply_control_settings(options, request.settings)
    return options


def _apply_control_settings(options: SDKOptions, settings: dict[str, Any]) -> SDKOptions:
    values = options.model_dump()
    if "model" in settings:
        values["model"] = str(settings.get("model") or "") or None
    if "permissionMode" in settings:
        values["permission_mode"] = str(settings.get("permissionMode") or "") or None
    if "permission_mode" in settings:
        values["permission_mode"] = str(settings.get("permission_mode") or "") or None
    if "systemPrompt" in settings:
        values["system_prompt"] = str(settings.get("systemPrompt") or "") or None
    if "system_prompt" in settings:
        values["system_prompt"] = str(settings.get("system_prompt") or "") or None
    metadata = dict(values.get("metadata") or {})
    metadata["flagSettings"] = dict(settings)
    values["metadata"] = metadata
    return SDKOptions.model_validate(values)


def _coerce_list_sessions_options(options: SDKListSessionsOptions | dict[str, Any] | None) -> SDKListSessionsOptions:
    if options is None:
        return SDKListSessionsOptions()
    if isinstance(options, SDKListSessionsOptions):
        return options
    return SDKListSessionsOptions.model_validate(options)


def _coerce_get_session_messages_options(
    options: SDKGetSessionMessagesOptions | dict[str, Any] | None,
) -> SDKGetSessionMessagesOptions:
    if options is None:
        return SDKGetSessionMessagesOptions()
    if isinstance(options, SDKGetSessionMessagesOptions):
        return options
    return SDKGetSessionMessagesOptions.model_validate(options)


def _coerce_fork_session_options(options: SDKForkSessionOptions | dict[str, Any] | None) -> SDKForkSessionOptions:
    if options is None:
        return SDKForkSessionOptions()
    if isinstance(options, SDKForkSessionOptions):
        return options
    return SDKForkSessionOptions.model_validate(options)


def _spec_from_options(options: SDKOptions) -> AgentSpec:
    spec = AgentSpec.from_overrides(
        model=options.model,
        protocol=options.protocol,
        workspace_path=options.cwd,
        enabled_tools=options.allowed_tools,
        skills=options.skills,
        system_prompt=options.system_prompt,
        permission_profile=options.permission_mode,
        agent_id=options.agent_id,
        tenant_id=options.tenant_id,
        user_id=options.user_id,
    )
    metadata = dict(options.metadata or {})
    structured_schema = _structured_output_schema_from_options(options)
    if structured_schema is not None:
        metadata["structured_output_schema"] = structured_schema
    if metadata:
        spec = replace(spec, metadata=metadata)
    return spec


def _structured_output_schema_from_options(options: SDKOptions) -> dict[str, Any] | None:
    output_format = options.output_format
    if not isinstance(output_format, dict):
        return None
    if output_format.get("type") != "json_schema":
        return None
    schema = output_format.get("schema")
    return dict(schema) if isinstance(schema, dict) else None
