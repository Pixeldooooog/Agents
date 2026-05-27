from __future__ import annotations

import inspect
from typing import Any

from agents.sdk.control import SDKControlElicitationRequest, SDKHookCallbackRequest


class SDKControlInteractionsMixin:
    async def _hook_callback_control_response(self, request: SDKHookCallbackRequest) -> dict[str, Any]:
        handler = self.hook_callback_handlers.get(request.callback_id)
        if handler is None:
            return {}
        response = handler(request)
        if inspect.isawaitable(response):
            response = await response
        if response is None:
            return {}
        if not isinstance(response, dict):
            raise TypeError("hook callback handler must return a dict")
        return dict(response)

    async def _elicitation_control_response(self, request: SDKControlElicitationRequest) -> dict[str, Any]:
        return await self._run_elicitation_handler(request)

    async def _run_elicitation_handler(self, request: SDKControlElicitationRequest) -> dict[str, Any]:
        if self.elicitation_handler is None:
            return {"action": "cancel"}
        response = self.elicitation_handler(request)
        if inspect.isawaitable(response):
            response = await response
        if response is None:
            return {"action": "cancel"}
        if not isinstance(response, dict):
            raise TypeError("elicitation handler must return a dict")
        action = str(response.get("action") or "cancel")
        if action not in {"accept", "decline", "cancel"}:
            raise ValueError("elicitation action must be accept, decline, or cancel")
        payload: dict[str, Any] = {"action": action}
        content = response.get("content")
        if content is not None:
            if not isinstance(content, dict):
                raise TypeError("elicitation content must be a dict")
            payload["content"] = dict(content)
        return payload
