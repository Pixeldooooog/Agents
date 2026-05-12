from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.tools.builtin.agents import agent_run
from agents.kernel.capabilities.tools.builtin.tasks import task_run
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.workflows import WorkflowEdge, WorkflowNode, WorkflowNodeKind, WorkflowPlan


WORKFLOW_VALIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": [kind.value for kind in WorkflowNodeKind]},
                    "name": {"type": "string"},
                    "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
                },
                "required": ["kind", "name"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "condition": {"type": "string"},
                },
                "required": ["source", "target"],
            },
        },
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["nodes"],
}

WORKFLOW_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        **WORKFLOW_VALIDATE_SCHEMA["properties"],
        "stop_on_error": {"type": "boolean"},
    },
    "required": ["nodes"],
}

WORKFLOW_TEMPLATES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional text filter over saved workflow name and metadata."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

WORKFLOW_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Saved workflow name without .json."},
    },
    "required": ["name"],
}

WORKFLOW_SAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Saved workflow name without .json."},
        **WORKFLOW_VALIDATE_SCHEMA["properties"],
        "overwrite": {"type": "boolean", "description": "Allow replacing an existing saved workflow."},
    },
    "required": ["name", "nodes"],
}

WORKFLOW_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Saved workflow name without .json."},
    },
    "required": ["name"],
}

WORKFLOW_RUN_SAVED_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Saved workflow name without .json."},
        "stop_on_error": {"type": "boolean"},
    },
    "required": ["name"],
}


def workflow_templates(
    context: ToolRuntimeContext,
    query: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    workflows = _list_saved_workflows(context)
    needle = str(query or "").strip().lower()
    if needle:
        workflows = [workflow for workflow in workflows if needle in _workflow_haystack(workflow)]
    limit = max(1, min(int(max_results or 50), 100))
    return {"workflows": workflows[:limit], "count": min(len(workflows), limit), "total": len(workflows)}


def workflow_read(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    workflow_name = _safe_workflow_name(name)
    result = context.sandbox_client.read_text(_workflow_template_path(workflow_name), max_bytes=200000)
    payload = _parse_workflow_json(result.content, workflow_name)
    return {"name": workflow_name, "path": result.path, "workflow": payload}


def workflow_save(
    context: ToolRuntimeContext,
    name: str,
    nodes: list[dict[str, Any]],
    workflow_id: str = "",
    edges: list[dict[str, Any]] | None = None,
    metadata: dict[str, str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    workflow_name = _safe_workflow_name(name)
    path = _workflow_template_path(workflow_name)
    if not overwrite and _workflow_exists(context, workflow_name):
        raise FileExistsError("workflow already exists: %s" % workflow_name)
    plan, raw_nodes = _workflow_plan(workflow_id=workflow_id or workflow_name, nodes=nodes, edges=edges, metadata=metadata)
    plan.validate()
    payload = {
        **_workflow_payload(plan),
        "nodes": [_node_payload(node, raw_nodes[node.node_id]) for node in plan.nodes],
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    result = context.sandbox_client.write_text(path, content)
    return {
        "name": workflow_name,
        "path": result.path,
        "bytes": result.bytes,
        "workflow": _workflow_summary(workflow_name, result.path, payload),
    }


def workflow_delete(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    workflow_name = _safe_workflow_name(name)
    path = _workflow_template_path(workflow_name)
    result = context.sandbox_client.delete_path(path)
    return {"name": workflow_name, "path": path, "deleted": bool(result.get("deleted", True)), "result": result}


async def workflow_run_saved(
    context: ToolRuntimeContext,
    name: str,
    stop_on_error: bool = True,
) -> dict[str, Any]:
    workflow_name = _safe_workflow_name(name)
    payload = workflow_read(context, workflow_name)["workflow"]
    ran = await workflow_run(
        context,
        nodes=list(payload.get("nodes") or []),
        workflow_id=str(payload.get("workflow_id") or workflow_name),
        edges=list(payload.get("edges") or []),
        metadata=dict(payload.get("metadata") or {}),
        stop_on_error=stop_on_error,
    )
    return {"name": workflow_name, "path": _workflow_template_path(workflow_name), **ran}


async def workflow_validate(
    context: ToolRuntimeContext,
    nodes: list[dict[str, Any]],
    workflow_id: str = "",
    edges: list[dict[str, Any]] | None = None,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    plan, raw_nodes = _workflow_plan(workflow_id=workflow_id, nodes=nodes, edges=edges, metadata=metadata)
    plan.validate()
    return {
        "workflow": _workflow_payload(plan),
        "order": [node.node_id for node in plan.topological_nodes()],
        "nodes": [_node_payload(node, raw_nodes[node.node_id]) for node in plan.topological_nodes()],
    }


async def workflow_run(
    context: ToolRuntimeContext,
    nodes: list[dict[str, Any]],
    workflow_id: str = "",
    edges: list[dict[str, Any]] | None = None,
    metadata: dict[str, str] | None = None,
    stop_on_error: bool = True,
) -> dict[str, Any]:
    plan, raw_nodes = _workflow_plan(workflow_id=workflow_id, nodes=nodes, edges=edges, metadata=metadata)
    plan.validate()
    results: list[dict[str, Any]] = []
    for node in plan.topological_nodes():
        raw = raw_nodes[node.node_id]
        result = await _run_node(context, node, raw)
        results.append(result)
        status = str(result.get("status") or "")
        if status in {"awaiting_approval", "error"} and bool(stop_on_error):
            return {"workflow": _workflow_payload(plan), "status": status, "results": results}
    return {"workflow": _workflow_payload(plan), "status": _workflow_status(results), "results": results}


async def _run_node(context: ToolRuntimeContext, node: WorkflowNode, raw: dict[str, Any]) -> dict[str, Any]:
    if node.kind == WorkflowNodeKind.HUMAN_APPROVAL:
        return {
            "node_id": node.node_id,
            "kind": node.kind.value,
            "name": node.name,
            "status": "awaiting_approval",
            "message": str(raw.get("input") or raw.get("prompt") or node.name),
        }
    if node.kind == WorkflowNodeKind.TASK:
        payload = await task_run(
            context,
            title=node.name,
            input=str(raw.get("input") or raw.get("prompt") or node.name),
            metadata={**node.metadata, "workflow_node_id": node.node_id},
            step_name=node.node_id,
        )
        return {
            "node_id": node.node_id,
            "kind": node.kind.value,
            "name": node.name,
            "status": payload["result"]["status"],
            "task": payload["task"],
            "step": payload["step"],
            "run": payload["run"],
            "content": payload["result"]["content"],
        }
    if node.kind == WorkflowNodeKind.AGENT:
        enabled_tools = raw.get("enabled_tools")
        payload = await agent_run(
            context,
            prompt=str(raw.get("prompt") or raw.get("input") or node.name),
            description=node.name,
            agent_id=str(raw.get("agent_id") or node.metadata.get("agent_id") or ""),
            system_prompt=str(raw.get("system_prompt") or ""),
            enabled_tools=enabled_tools if isinstance(enabled_tools, list) else None,
        )
        return {
            "node_id": node.node_id,
            "kind": node.kind.value,
            "name": node.name,
            "status": payload["status"],
            "agent_id": payload["agent_id"],
            "run_id": payload["run_id"],
            "content": payload["content"],
        }
    return {
        "node_id": node.node_id,
        "kind": node.kind.value,
        "name": node.name,
        "status": "error",
        "error": "workflow node kind is not executable here: %s" % node.kind.value,
    }


def _workflow_plan(
    *,
    workflow_id: str = "",
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    metadata: dict[str, str] | None = None,
) -> tuple[WorkflowPlan, dict[str, dict[str, Any]]]:
    raw_nodes: dict[str, dict[str, Any]] = {}
    workflow_nodes: list[WorkflowNode] = []
    for index, raw in enumerate(nodes or [], start=1):
        node_id = _safe_node_id(str(raw.get("node_id") or raw.get("id") or "node_%d" % index))
        raw_nodes[node_id] = dict(raw)
        workflow_nodes.append(
            WorkflowNode(
                node_id=node_id,
                kind=WorkflowNodeKind(str(raw.get("kind") or "")),
                name=_required_text(str(raw.get("name") or ""), "name"),
                metadata=_string_metadata(raw.get("metadata")),
            )
        )
    plan = WorkflowPlan(
        workflow_id=str(workflow_id or "workflow"),
        nodes=workflow_nodes,
        edges=[
            WorkflowEdge(
                source=_safe_node_id(str(edge.get("source") or "")),
                target=_safe_node_id(str(edge.get("target") or "")),
                condition=str(edge.get("condition") or ""),
            )
            for edge in edges or []
        ],
        metadata=_string_metadata(metadata),
    )
    return plan, raw_nodes


def _workflow_payload(plan: WorkflowPlan) -> dict[str, Any]:
    return {
        "workflow_id": plan.workflow_id,
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind.value,
                "name": node.name,
                "metadata": dict(node.metadata),
            }
            for node in plan.nodes
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "condition": edge.condition}
            for edge in plan.edges
        ],
        "metadata": dict(plan.metadata),
    }


def _node_payload(node: WorkflowNode, raw: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "node_id": node.node_id,
        "kind": node.kind.value,
        "name": node.name,
        "metadata": dict(node.metadata),
    }
    for key in ["input", "prompt", "agent_id", "system_prompt", "enabled_tools"]:
        if key in raw:
            payload[key] = raw[key]
    return payload


def _workflow_status(results: list[dict[str, Any]]) -> str:
    statuses = {str(result.get("status") or "") for result in results}
    if "error" in statuses:
        return "error"
    if "awaiting_approval" in statuses:
        return "awaiting_approval"
    return "finished"


def _string_metadata(metadata: Any) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _safe_node_id(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "_" for ch in str(value or "").strip())
    return text.strip("._-") or "node"


def _list_saved_workflows(context: ToolRuntimeContext) -> list[dict[str, Any]]:
    try:
        listing = context.sandbox_client.list_dir(".agents/workflows")
    except Exception:  # noqa: BLE001 - missing workflow directory simply means no saved workflows.
        return []
    workflows: list[dict[str, Any]] = []
    for entry in listing.entries:
        if entry.type != "file" or not entry.name.endswith(".json"):
            continue
        name = entry.name[:-5]
        try:
            read = context.sandbox_client.read_text(entry.path, max_bytes=200000)
            payload = _parse_workflow_json(read.content, name)
            workflows.append(_workflow_summary(name, entry.path, payload))
        except Exception as exc:  # noqa: BLE001 - broken workflow files should remain visible.
            workflows.append({"name": name, "path": entry.path, "error": str(exc)})
    return sorted(workflows, key=lambda item: item["name"])


def _workflow_exists(context: ToolRuntimeContext, name: str) -> bool:
    try:
        context.sandbox_client.read_text(_workflow_template_path(name), max_bytes=1)
        return True
    except Exception:  # noqa: BLE001 - any read failure here means overwrite protection can allow creation.
        return False


def _parse_workflow_json(content: str, name: str) -> dict[str, Any]:
    payload = json.loads(content or "{}")
    if not isinstance(payload, dict):
        raise ValueError("workflow must be a JSON object: %s" % name)
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("workflow nodes must be a list: %s" % name)
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    metadata = _string_metadata(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {})
    plan, raw_nodes = _workflow_plan(
        workflow_id=str(payload.get("workflow_id") or name),
        nodes=[dict(node) for node in nodes if isinstance(node, dict)],
        edges=[dict(edge) for edge in edges if isinstance(edge, dict)],
        metadata=metadata,
    )
    plan.validate()
    return {
        **_workflow_payload(plan),
        "nodes": [_node_payload(node, raw_nodes[node.node_id]) for node in plan.nodes],
    }


def _workflow_summary(name: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    preview = ", ".join(str(node.get("name") or node.get("node_id") or "") for node in nodes if isinstance(node, dict))
    return {
        "name": name,
        "path": path,
        "workflow_id": str(payload.get("workflow_id") or name),
        "node_count": len(nodes),
        "metadata": _string_metadata(metadata),
        "preview": preview[:160],
    }


def _workflow_haystack(workflow: dict[str, Any]) -> str:
    return " ".join(
        [
            str(workflow.get("name") or ""),
            str(workflow.get("workflow_id") or ""),
            str(workflow.get("preview") or ""),
            " ".join("%s %s" % (key, value) for key, value in dict(workflow.get("metadata") or {}).items()),
            str(workflow.get("error") or ""),
        ]
    ).lower()


def _workflow_template_path(name: str) -> str:
    return ".agents/workflows/%s.json" % name


def _safe_workflow_name(value: Any) -> str:
    text = str(value or "").strip()
    name = "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")
    if not name:
        raise ValueError("name is required")
    if "/" in text or "\\" in text or name in {".", ".."}:
        raise ValueError("workflow name must not contain path separators")
    return name
