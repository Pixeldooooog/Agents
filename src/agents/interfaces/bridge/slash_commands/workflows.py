from __future__ import annotations

import json
from typing import Any

from agents.interfaces.bridge.payloads import workflows_payload
from agents.interfaces.bridge.slash_commands.common import BridgeWriter, split_once, split_once_preserve, tool_context
from agents.kernel.capabilities.tools.builtin.workflows import (
    workflow_delete,
    workflow_read,
    workflow_run_saved,
    workflow_save,
    workflow_validate,
)


async def handle_workflows_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action or action in {"list", "ls"}:
        write({"type": "workflows", "workflows": workflows_payload(state)})
        return
    if action in {"read", "show", "view"}:
        _handle_workflow_read(state, rest, write=write)
        return
    if action == "save":
        _handle_workflow_save(state, rest, write=write)
        return
    if action in {"delete", "remove", "rm"}:
        _handle_workflow_delete(state, rest, write=write)
        return
    if action in {"run", "start"}:
        await _handle_workflow_run(state, rest, write=write)
        return
    if action == "validate":
        await _handle_workflow_validate(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown workflows command: %s" % action})


def _handle_workflow_read(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    name = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not name:
        write({"type": "error", "message": "usage: /workflows read <name>"})
        return
    try:
        payload = workflow_read(context, name)
    except Exception as exc:  # noqa: BLE001 - slash commands should surface file/validation errors.
        write({"type": "error", "message": "workflow read failed: %s" % exc})
        return
    write({"type": "workflows", "workflows": _workflow_detail_rows(payload)})


def _handle_workflow_save(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    name, content = split_once_preserve(rest)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not name or not content.strip():
        write({"type": "error", "message": "usage: /workflows save <name> <workflow_json>"})
        return
    try:
        payload = _parse_workflow_json_arg(content)
        saved = workflow_save(
            context,
            name=name,
            workflow_id=str(payload.get("workflow_id") or name),
            nodes=list(payload.get("nodes") or []),
            edges=list(payload.get("edges") or []),
            metadata=dict(payload.get("metadata") or {}),
            overwrite=bool(payload.get("overwrite", False)),
        )
    except Exception as exc:  # noqa: BLE001 - validation and sandbox errors are command output.
        write({"type": "error", "message": "workflow save failed: %s" % exc})
        return
    write({"type": "notice", "message": "workflow saved: %s" % saved["name"]})
    write({"type": "workflows", "workflows": workflows_payload(state)})


def _handle_workflow_delete(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    name = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not name:
        write({"type": "error", "message": "usage: /workflows delete <name>"})
        return
    try:
        deleted = workflow_delete(context, name)
    except Exception as exc:  # noqa: BLE001 - validation and sandbox errors are command output.
        write({"type": "error", "message": "workflow delete failed: %s" % exc})
        return
    if not deleted.get("deleted"):
        write({"type": "error", "message": "workflow not found: %s" % deleted["name"]})
        return
    write({"type": "notice", "message": "workflow deleted: %s" % deleted["name"]})
    write({"type": "workflows", "workflows": workflows_payload(state)})


async def _handle_workflow_run(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    name = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not name:
        write({"type": "error", "message": "usage: /workflows run <name>"})
        return
    try:
        result = await workflow_run_saved(context, name)
    except Exception as exc:  # noqa: BLE001 - workflow runtime failures are command output.
        write({"type": "error", "message": "workflow run failed: %s" % exc})
        return
    write({"type": "notice", "message": "workflow %s: %s" % (result["name"], result["status"])})
    write({"type": "workflows", "workflows": _workflow_result_rows(result)})


async def _handle_workflow_validate(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    name = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not name:
        write({"type": "error", "message": "usage: /workflows validate <name>"})
        return
    try:
        payload = workflow_read(context, name)["workflow"]
        validated = await workflow_validate(
            context,
            nodes=list(payload.get("nodes") or []),
            workflow_id=str(payload.get("workflow_id") or name),
            edges=list(payload.get("edges") or []),
            metadata=dict(payload.get("metadata") or {}),
        )
    except Exception as exc:  # noqa: BLE001 - validation errors are command output.
        write({"type": "error", "message": "workflow validation failed: %s" % exc})
        return
    write({"type": "workflows", "workflows": [["order", " -> ".join(validated["order"])], ["nodes", str(len(validated["nodes"]))]]})


def _parse_workflow_json_arg(value: str) -> dict[str, Any]:
    raw = json.loads(value)
    if isinstance(raw, list):
        return {"nodes": raw}
    if not isinstance(raw, dict):
        raise ValueError("workflow JSON must be an object or node array")
    if not isinstance(raw.get("nodes"), list):
        raise ValueError("workflow JSON must include nodes")
    return raw


def _workflow_detail_rows(payload: dict[str, Any]) -> list[list[str]]:
    workflow = dict(payload.get("workflow") or {})
    rows = [
        ["name", str(payload.get("name") or "")],
        ["workflow_id", str(workflow.get("workflow_id") or "")],
        ["path", str(payload.get("path") or "")],
        ["nodes", str(len(workflow.get("nodes") or []))],
    ]
    metadata = workflow.get("metadata") if isinstance(workflow.get("metadata"), dict) else {}
    if metadata:
        rows.append(["metadata", ", ".join("%s=%s" % (key, value) for key, value in sorted(metadata.items()))])
    for node in list(workflow.get("nodes") or [])[:20]:
        if not isinstance(node, dict):
            continue
        detail = " · ".join(
            part
            for part in [
                str(node.get("kind") or ""),
                str(node.get("name") or ""),
                _compact_workflow_text(str(node.get("input") or node.get("prompt") or "")),
            ]
            if part
        )
        rows.append([str(node.get("node_id") or "node"), detail])
    return rows


def _workflow_result_rows(result: dict[str, Any]) -> list[list[str]]:
    workflow = dict(result.get("workflow") or {})
    rows = [
        ["workflow", str(workflow.get("workflow_id") or result.get("name") or "")],
        ["status", str(result.get("status") or "")],
    ]
    for node_result in list(result.get("results") or [])[:30]:
        if not isinstance(node_result, dict):
            continue
        detail = " · ".join(
            part
            for part in [
                str(node_result.get("kind") or ""),
                str(node_result.get("status") or ""),
                _compact_workflow_text(str(node_result.get("content") or node_result.get("message") or node_result.get("error") or "")),
            ]
            if part
        )
        rows.append([str(node_result.get("node_id") or "node"), detail])
    return rows


def _compact_workflow_text(value: str, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
