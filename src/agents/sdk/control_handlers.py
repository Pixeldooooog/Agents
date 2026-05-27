from __future__ import annotations

from typing import Any

from agents.sdk.control import (
    SDKControlApplyFlagSettingsRequest,
    SDKControlCancelAsyncMessageRequest,
    SDKControlElicitationRequest,
    SDKControlErrorResponse,
    SDKControlGetContextUsageRequest,
    SDKControlGetSettingsRequest,
    SDKControlInitializeRequest,
    SDKControlInterruptRequest,
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpStatusRequest,
    SDKControlMcpToggleRequest,
    SDKControlPermissionRequest,
    SDKControlReloadPluginsRequest,
    SDKControlRequest,
    SDKControlRequestInner,
    SDKControlResponse,
    SDKControlResponseInner,
    SDKControlRewindFilesRequest,
    SDKControlSeedReadStateRequest,
    SDKControlSetMaxThinkingTokensRequest,
    SDKControlSetModelRequest,
    SDKControlSetPermissionModeRequest,
    SDKControlStopTaskRequest,
    SDKControlSuccessResponse,
    SDKHookCallbackRequest,
    validate_sdk_control_request,
)
from agents.sdk.control_async_state import SDKControlAsyncStateMixin
from agents.sdk.control_files import SDKControlFilesMixin
from agents.sdk.control_interactions import SDKControlInteractionsMixin
from agents.sdk.control_mcp import SDKControlMcpMixin
from agents.sdk.control_payloads import (
    _empty_context_usage_payload,
    _initialize_control_response_payload,
    _permission_control_response_payload,
    _settings_control_response_payload,
    _slash_command_infos,
)
from agents.sdk.control_system import SDKControlSystemMessagesMixin
from agents.sdk.control_tasks import SDKControlTasksMixin
from agents.sdk.options import _apply_control_settings, _coerce_options
from agents.sdk.types import SDKOptions


class SDKControlHandlersMixin(
    SDKControlAsyncStateMixin,
    SDKControlFilesMixin,
    SDKControlMcpMixin,
    SDKControlInteractionsMixin,
    SDKControlTasksMixin,
    SDKControlSystemMessagesMixin,
):
    async def handle_control_request(
        self,
        message: SDKControlRequest | dict[str, Any],
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> SDKControlResponse:
        control = validate_sdk_control_request(message)
        resolved_options = _coerce_options(options)
        try:
            payload = await self._control_response_payload(control.request, resolved_options)
            response: SDKControlResponseInner = SDKControlSuccessResponse(
                request_id=control.request_id,
                response=payload,
            )
        except Exception as exc:
            response = SDKControlErrorResponse(request_id=control.request_id, error=str(exc))
        return SDKControlResponse(response=response)

    async def _control_response_payload(
        self,
        request: SDKControlRequestInner,
        options: SDKOptions,
    ) -> dict[str, Any]:
        if isinstance(request, SDKControlInitializeRequest):
            return _initialize_control_response_payload(self.settings, options, request)
        if isinstance(request, SDKControlMcpStatusRequest):
            return {"mcpServers": await self._mcp_statuses_for_options(options)}
        if isinstance(request, SDKControlPermissionRequest):
            return await _permission_control_response_payload(request, options)
        if isinstance(request, SDKControlSetModelRequest):
            return {"model": request.model or ""}
        if isinstance(request, SDKControlSetPermissionModeRequest):
            return {"mode": request.mode, "ultraplan": bool(request.ultraplan or False)}
        if isinstance(request, SDKControlSetMaxThinkingTokensRequest):
            return {"max_thinking_tokens": request.max_thinking_tokens}
        if isinstance(request, SDKControlGetSettingsRequest):
            return _settings_control_response_payload(options)
        if isinstance(request, SDKControlApplyFlagSettingsRequest):
            updated = _apply_control_settings(options, request.settings)
            return _settings_control_response_payload(updated)
        if isinstance(request, SDKControlMcpSetServersRequest):
            return await self._mcp_set_servers_control_response(request, options)
        if isinstance(request, SDKControlMcpToggleRequest):
            return await self._mcp_toggle_control_response(request, options)
        if isinstance(request, SDKControlMcpReconnectRequest):
            return await self._mcp_reconnect_control_response(request, options)
        if isinstance(request, SDKControlInterruptRequest):
            return self._interrupt_control_response(options)
        if isinstance(request, SDKControlGetContextUsageRequest):
            return _empty_context_usage_payload(options)
        if isinstance(request, SDKHookCallbackRequest):
            return await self._hook_callback_control_response(request)
        if isinstance(request, SDKControlReloadPluginsRequest):
            return {"commands": _slash_command_infos(), "agents": [], "plugins": [], "mcpServers": [], "error_count": 0}
        if isinstance(request, SDKControlCancelAsyncMessageRequest):
            return self._cancel_async_message_control_response(request)
        if isinstance(request, SDKControlRewindFilesRequest):
            return await self._rewind_files_control_response(request, options)
        if isinstance(request, SDKControlSeedReadStateRequest):
            return await self._seed_read_state_control_response(request, options)
        if isinstance(request, SDKControlMcpMessageRequest):
            return await self._mcp_message_control_response(request, options)
        if isinstance(request, SDKControlStopTaskRequest):
            return await self._stop_task_control_response(request, options)
        if isinstance(request, SDKControlElicitationRequest):
            return await self._elicitation_control_response(request)
        return {}
