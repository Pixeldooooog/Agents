from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agents.interfaces.bridge.slash_commands.common import BridgeWriter, error_message
from agents.kernel.governance.permissions import ToolPermissionDecision
from agents.kernel.schema import ToolCall


async def execute_slash_tool(
    state: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    write: BridgeWriter,
    error_label: str,
    fallback: Callable[[], Any] | None = None,
) -> dict[str, Any] | None:
    runtime = getattr(getattr(state, "session", None), "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    if orchestrator is None:
        return await _execute_slash_fallback(fallback, write=write, error_label=error_label)

    call = ToolCall(
        id="slash_%s" % uuid4().hex[:12],
        name=tool_name,
        arguments=dict(arguments or {}),
        raw={"source": "slash"},
    )
    try:
        authorizations = await orchestrator.authorize([call])
    except Exception as exc:  # noqa: BLE001 - policy failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, error_message(exc))})
        return None
    if not authorizations:
        write({"type": "error", "message": "%s failed: missing permission decision" % error_label})
        return None

    decision = authorizations[0].decision
    if not decision.allowed and decision.requires_approval:
        decision = ToolPermissionDecision(
            allowed=True,
            reason=decision.reason,
            metadata={"source": "slash", "approval": "explicit_command"},
        )
    if not decision.allowed:
        reason = decision.reason or "tool call denied by permission policy"
        write({"type": "error", "message": "%s failed: %s" % (error_label, reason)})
        return None

    try:
        batch = await orchestrator.execute_with_decisions(
            [call],
            [decision],
            run_id="slash_%s" % uuid4().hex[:8],
        )
    except Exception as exc:  # noqa: BLE001 - registry failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, error_message(exc))})
        return None
    if not batch.results:
        write({"type": "error", "message": "%s failed: no tool result returned" % error_label})
        return None
    result = batch.results[0]
    if result.is_error:
        if fallback is not None and str(result.content or "").strip().startswith("unknown tool:"):
            return await _execute_slash_fallback(fallback, write=write, error_label=error_label)
        message = str(result.content or "").strip() or "tool execution failed"
        write({"type": "error", "message": "%s failed: %s" % (error_label, message)})
        return None
    return _tool_result_payload(result.raw, result.content)


async def _execute_slash_fallback(
    fallback: Callable[[], Any] | None,
    *,
    write: BridgeWriter,
    error_label: str,
) -> dict[str, Any] | None:
    if fallback is None:
        write({"type": "error", "message": "%s failed: runtime tool orchestration is not available" % error_label})
        return None
    try:
        result = fallback()
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as exc:  # noqa: BLE001 - fallback failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, error_message(exc))})
        return None
    return _tool_result_payload(result, "")


def _tool_result_payload(raw: Any, content: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(content or "").strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return dict(parsed)
            return {"result": parsed}
        except Exception:
            return {"result": text}
    if isinstance(raw, str):
        return {"result": raw}
    if raw is None:
        return {}
    return {"result": raw}
