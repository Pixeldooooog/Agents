from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agents.interfaces.bridge.sessions import TerminalSessionRecord, session_model_label
from agents.kernel.config import active_profile_name
from agents.kernel.config.paths import ENV_FILE
from agents.kernel.governance import classify_tool_risk
from agents.kernel.schema import ToolSpec
from agents.kernel.schema import Message
from agents.kernel.capabilities.tools.builtin.commands import command_discover
from agents.kernel.capabilities.tools.builtin.workflows import workflow_templates
from agents.platform.commands import COMMANDS, SlashCommand


def runtime_payload(state: Any) -> dict[str, Any]:
    return {
        "protocol": str(state.session.runtime.protocol),
        "model": str(state.session.runtime.model),
        "model_profile": active_profile_name(
            state.model_profiles,
            state.session.runtime.protocol,
            state.session.runtime.model,
            model_base_url(state.session),
        ),
        "endpoint": model_endpoint(state.session),
    }


def model_profiles_payload(state: Any) -> list[dict[str, Any]]:
    active_protocol = str(state.session.runtime.protocol)
    active_model = str(state.session.runtime.model)
    active_base_url = model_base_url(state.session).rstrip("/")
    rows = []
    for profile in state.model_profiles:
        profile_base_url = str(profile.base_url or "").rstrip("/")
        rows.append(
            {
                "name": profile.name,
                "protocol": profile.protocol,
                "model": profile.model,
                "endpoint": profile.endpoint,
                "configured": profile.configured,
                "active": profile.protocol == active_protocol
                and profile.model == active_model
                and (not active_base_url or not profile_base_url or profile_base_url == active_base_url),
            }
        )
    return rows


def commands_payload(commands: list[SlashCommand]) -> list[dict[str, Any]]:
    return [
        {
            "name": command.name,
            "description": command.action,
            "action": command.action,
            "aliases": list(command.aliases),
            "argumentHint": command.argument_hint,
            "availability": command.availability,
            "source": command.source,
            "category": command.category,
        }
        for command in commands
    ]


def commands_payload_for_state(state: Any) -> list[dict[str, Any]]:
    rows = commands_payload(COMMANDS)
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return rows
    try:
        custom = command_discover(context, max_results=100).get("commands", [])
    except Exception:
        return rows
    rows.extend(
        {
            "name": command["name"],
            "description": command.get("description", ""),
            "action": command.get("description", ""),
            "aliases": list(command.get("aliases") or []),
            "argumentHint": command.get("argumentHint", ""),
            "availability": "idle",
            "source": command.get("source", "workspace"),
            "category": command.get("category", "custom"),
        }
        for command in custom
    )
    return rows


def workspace_payload(state: Any) -> dict[str, Any]:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None:
        return {"path": "", "display": "no workspace"}
    path = str(getattr(workspace, "path", "") or getattr(state, "active_workspace", "") or "")
    return {
        "path": path,
        "display": short_path(path) if path else "no workspace path",
        "tenant_id": getattr(workspace, "tenant_id", ""),
        "user_id": getattr(workspace, "user_id", ""),
        "agent_id": getattr(workspace, "agent_id", ""),
        "workspace_id": getattr(workspace, "workspace_id", ""),
    }


def status_payload(state: Any) -> dict[str, str]:
    payload = {
        "session": short_session_id(state.session_id),
        "model": "%s · %s" % (state.session.runtime.protocol, state.session.runtime.model),
        "profile": state.profile,
        "permission": state.permission,
        "messages": str(max(0, len(getattr(state.session, "messages", [])) - 1)),
        "tokens": estimate_session_tokens(state.session),
        "tools": str(len(state.active_tools)),
    }
    endpoint = model_endpoint(state.session)
    if endpoint:
        payload["endpoint"] = endpoint
    return payload


def context_payload(state: Any) -> dict[str, str]:
    return {
        "tokens": estimate_session_tokens(state.session),
        "limit": str(getattr(state.session, "max_context_tokens", "")),
        "messages": str(len(getattr(state.session, "messages", []))),
        "trace_items": str(len(getattr(state.session, "context_trace", []))),
    }


def doctor_payload(state: Any) -> dict[str, str]:
    return {
        "env_file": ENV_FILE,
        "model": "%s · %s" % (state.session.runtime.protocol, state.session.runtime.model),
        "endpoint": model_endpoint(state.session) or "not exposed",
        "timeout": str(getattr(state.settings.agent, "TIMEOUT", "")),
        "max_retries": str(getattr(state.settings.agent, "MAX_RETRIES", "")),
        "retry_base_delay": str(getattr(state.settings.agent, "RETRY_BASE_DELAY", "")),
        "configured_profiles": str(len([profile for profile in state.model_profiles if profile.configured])),
        "enabled_tools": str(len(state.active_tools)),
        "workspace": workspace_payload(state).get("path", "not bound"),
        "sessions": str(state.session_store.root),
    }


def trace_payload(state: Any) -> list[list[str]]:
    trace = list(getattr(state.session, "context_trace", []) or [])
    rows: list[list[str]] = []
    for item in trace[:30]:
        layer = getattr(getattr(item, "layer", ""), "value", getattr(item, "layer", ""))
        source = str(getattr(item, "source", ""))
        status = "in" if bool(getattr(item, "included", False)) else "out"
        tokens = str(getattr(item, "tokens", ""))
        reason = str(getattr(item, "reason", ""))
        rows.append([str(layer), "%s · %s tokens · %s%s" % (source, tokens, status, (" · " + reason) if reason else "")])
    if len(trace) > 30:
        rows.append(["...", "%s more" % (len(trace) - 30)])
    if not rows:
        rows.append(["trace", "not available"])
    return rows


def prompt_payload(state: Any) -> list[list[str]]:
    prompt = str(getattr(state.session, "system_prompt", "") or "")
    trace = list(getattr(state.session, "context_trace", []) or [])
    included = [item for item in trace if bool(getattr(item, "included", False))]
    dropped = [item for item in trace if not bool(getattr(item, "included", False))]
    rows = [
        ["system_chars", str(len(prompt))],
        ["source", "session_override" if bool(getattr(getattr(state.session, "tool_context", None), "system_prompt_overridden", False)) else "configured"],
        ["included_fragments", str(len(included))],
        ["dropped_fragments", str(len(dropped))],
        ["layers", _context_layer_counts(included)],
    ]
    if dropped:
        rows.append(["dropped", _join_limited([str(getattr(item, "id", "")) for item in dropped if getattr(item, "id", "")])])
    preview = _compact_text(prompt.replace("\n", " "), limit=160)
    if preview:
        rows.append(["preview", preview])
    return rows


def session_payload(state: Any) -> list[list[str]]:
    workspace = workspace_payload(state)
    saved_sessions = _safe_len(lambda: state.session_store.list())
    runtime = getattr(state.session, "runtime", None)
    return [
        ["session", short_session_id(state.session_id)],
        ["profile", str(getattr(state, "profile", ""))],
        ["model", "%s · %s" % (getattr(runtime, "protocol", ""), getattr(runtime, "model", ""))],
        ["permission", "%s -> %s" % (getattr(state, "permission", ""), getattr(state, "permission_mode", ""))],
        ["workspace", str(workspace.get("display", ""))],
        ["messages", str(max(0, len(getattr(state.session, "messages", [])) - 1))],
        ["context_tokens", estimate_session_tokens(state.session)],
        ["active_run", str(getattr(state, "active_run_id", "") or "none")],
        ["saved_sessions", str(saved_sessions)],
    ]


async def agents_payload(state: Any) -> list[list[str]]:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not workspace.tenant_id or not workspace.user_id:
        return [["agents", "identity scope not available"]]
    store = getattr(getattr(state, "persistence", None), "agent_profiles", None)
    if store is None or not hasattr(store, "list_for_user"):
        return [["agents", "profile store not available"]]
    profiles = await store.list_for_user(workspace.tenant_id, workspace.user_id)
    if not profiles:
        return [["agents", "none visible to this user"]]
    rows: list[list[str]] = []
    for profile in profiles[:30]:
        rows.append([profile.agent_id, _agent_profile_detail(profile)])
    if len(profiles) > 30:
        rows.append(["...", "%s more" % (len(profiles) - 30)])
    return rows


async def tasks_payload(state: Any) -> list[list[str]]:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not workspace.tenant_id or not workspace.user_id:
        return [["tasks", "identity scope not available"]]
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    if store is None or not hasattr(store, "list_tasks"):
        return [["tasks", "task store not available"]]
    tasks = await store.list_tasks(workspace.tenant_id, user_id=workspace.user_id, agent_id=workspace.agent_id)
    if not tasks:
        return [["tasks", "none for current agent"]]
    rows: list[list[str]] = []
    for task in tasks[-30:]:
        rows.append([_short_task_id(getattr(task, "task_id", "")), _task_detail(task)])
    return rows


def schedules_payload(state: Any) -> list[list[str]]:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return [["schedules", "tool context not available"]]
    schedules = sorted(
        list((getattr(context, "scheduled_tasks", {}) or {}).values()),
        key=lambda item: float(item.get("updated_at") or 0),
        reverse=True,
    )
    rows: list[list[str]] = []
    for item in schedules[:30]:
        status = "enabled" if bool(item.get("enabled", True)) else "disabled"
        detail = " · ".join(
            part
            for part in [
                status,
                str(item.get("schedule") or ""),
                str(item.get("title") or ""),
                ("last: " + str(item.get("last_run_task_id"))) if item.get("last_run_task_id") else "",
            ]
            if part
        )
        rows.append([str(item.get("short_id") or item.get("schedule_id") or "schedule"), detail])
    return rows or [["schedules", "none"]]


def hooks_payload(state: Any) -> list[list[str]]:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    registry = getattr(context, "hook_registry", None)
    if registry is None:
        return [["hooks", "hook registry not available"]]
    rows: list[list[str]] = []
    for hook in registry.list(limit=30):
        status = "enabled" if hook.enabled else "disabled"
        tool = str(getattr(hook, "metadata", {}).get("tool") or getattr(hook, "metadata", {}).get("tool_name") or "")
        detail = " · ".join(part for part in [status, hook.event, hook.action, hook.name, tool] if part)
        rows.append([hook.short_id, detail])
    return rows or [["hooks", "none"]]


def todo_payload(state: Any) -> list[list[str]]:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return [["todos", "tool context not available"]]
    todos = list(getattr(context, "todos", []) or [])
    if not todos:
        return [["todos", "empty"]]
    rows: list[list[str]] = []
    for index, item in enumerate(todos, start=1):
        status = str(item.get("status") or "")
        content = _compact_text(str(item.get("content") or ""))
        active_form = _compact_text(str(item.get("activeForm") or item.get("active_form") or ""))
        detail = "%s · %s" % (status, active_form) if active_form else status
        rows.append(["%s. %s" % (index, content), detail])
    return rows


def plan_payload(state: Any) -> list[list[str]]:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return [["plan", "tool context not available"]]
    allowed = list(getattr(context, "plan_allowed_prompts", []) or [])
    rows = [
        ["mode", "plan" if getattr(context, "plan_mode", False) else "default"],
        ["last_plan", _compact_text(str(getattr(context, "plan_text", "") or ""), limit=160) or "-"],
        ["allowed_prompts", str(len(allowed))],
    ]
    for item in allowed[:10]:
        rows.append([str(item.get("tool") or "tool"), _compact_text(str(item.get("prompt") or ""), limit=120)])
    return rows


def capabilities_payload(state: Any) -> list[list[str]]:
    active_tools = [str(name) for name in getattr(state, "active_tools", [])]
    high_risk_tools = [
        name
        for name in active_tools
        if classify_tool_risk(name).value in {"high", "critical"}
    ]
    workspace = getattr(state.session, "workspace", None)
    return [
        ["commands", str(len(COMMANDS))],
        ["tools", "%s enabled · %s high risk" % (len(active_tools), len(high_risk_tools))],
        ["permissions", "%s -> %s" % (getattr(state, "permission", ""), getattr(state, "permission_mode", ""))],
        ["skills", "%s visible" % _catalog_count(skills_payload(state), "skills")],
        ["plugins", "%s visible" % _catalog_count(plugins_payload(state), "plugins")],
        ["mcp", _mcp_summary(state)],
        ["memory", "identity scoped" if workspace is not None and getattr(workspace, "tenant_id", "") and getattr(workspace, "user_id", "") else "identity unavailable"],
        ["sessions", "%s saved" % _safe_len(lambda: state.session_store.list())],
        ["agents", "store available" if hasattr(getattr(getattr(state, "persistence", None), "agent_profiles", None), "list_for_user") else "store unavailable"],
        ["tasks", "store available" if hasattr(getattr(getattr(state, "persistence", None), "tasks", None), "list_tasks") else "store unavailable"],
        ["schedules", "%s scope" % _catalog_count(schedules_payload(state), "schedules")],
        ["hooks", "%s session" % _catalog_count(hooks_payload(state), "hooks")],
        ["todos", "session state"],
        ["plan", "session state"],
        ["workflows", "%s saved" % _catalog_count(workflows_payload(state), "workflows")],
    ]


def workflows_payload(state: Any) -> list[list[str]]:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return [["workflows", "tool context not available"]]
    try:
        workflows = workflow_templates(context, max_results=50).get("workflows", [])
    except Exception as exc:  # noqa: BLE001 - keep slash status usable if a workflow file is broken.
        return [["workflows", "unavailable · %s" % exc]]
    rows: list[list[str]] = []
    for workflow in workflows:
        name = str(workflow.get("name") or "")
        if workflow.get("error"):
            rows.append([name, "invalid · %s" % workflow.get("error")])
            continue
        detail = "%s · %s node%s" % (
            workflow.get("workflow_id") or name,
            workflow.get("node_count", 0),
            "" if workflow.get("node_count") == 1 else "s",
        )
        preview = str(workflow.get("preview") or "")
        if preview:
            detail = "%s · %s" % (detail, _compact_text(preview, limit=120))
        rows.append([name, detail])
    return rows or [["workflows", "none saved"]]


def plugins_payload(state: Any) -> list[list[str]]:
    root = Path(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).expanduser()
    rows: list[list[str]] = []
    enabled = set(getattr(state, "enabled_plugins", set()) or set())
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        for manifest_path in sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")):
            rows.append(_plugin_manifest_row(manifest_path, enabled))
        for manifest_path in sorted(plugins_dir.glob("*/plugin.json")):
            rows.append(_plugin_manifest_row(manifest_path, enabled))
    if not rows:
        rows.append(["plugins", "none configured"])
    return rows


def skills_payload(state: Any) -> list[list[str]]:
    configured = set(_csv_setting(getattr(state.settings.agent, "SKILLS", ""))) | set(getattr(state, "enabled_skills", set()) or set())
    root = Path(getattr(state.settings.server, "ROOT_PATH", ".")).expanduser()
    skills_dir = root / "skills"
    rows: list[list[str]] = []
    seen: set[str] = set()

    manifest_paths = sorted([*skills_dir.glob("*.json"), *skills_dir.glob("*/skill.json")]) if skills_dir.exists() else []
    for manifest_path in manifest_paths:
        name = manifest_path.parent.name if manifest_path.name == "skill.json" else manifest_path.stem
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            seen.add(name)
            rows.append([name, "invalid manifest · %s" % exc])
            continue
        name = str(raw.get("name") or name)
        seen.add(name)
        tools = ", ".join(str(tool) for tool in raw.get("tools", [])[:4])
        status = "configured" if name in configured else "available"
        description = str(raw.get("description") or "")
        detail = " · ".join(part for part in [status, raw.get("version", ""), description, ("tools: " + tools) if tools else ""] if part)
        rows.append([name, detail])

    for name in sorted(configured - seen):
        rows.append([name, "configured · manifest missing"])
    if not rows:
        rows.append(["skills", "none configured"])
    return rows


def mcp_payload(state: Any) -> list[list[str]]:
    mcp_settings = getattr(getattr(state, "settings", None), "mcp", None)
    command = str(getattr(mcp_settings, "SERVER_COMMAND", "") or "").strip()
    if not command:
        return [["server", "not configured"]]
    mcp_tools = [name for name in state.active_tools if str(name).startswith("mcp_")]
    return [
        ["server", str(getattr(mcp_settings, "SERVER_NAME", "") or "default")],
        ["command", command],
        ["mode", str(getattr(mcp_settings, "EXECUTION_MODE", "") or "trusted_control_plane")],
        ["sandbox", str(getattr(mcp_settings, "SANDBOX_PROFILE", "") or "-")],
        ["tools", str(len(mcp_tools))],
    ]


def tools_payload(state: Any) -> list[list[str]]:
    active_tools = [str(name) for name in getattr(state, "active_tools", [])]
    if not active_tools:
        return [["tools", "none enabled"]]

    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    rows: list[list[str]] = []
    for name in active_tools:
        spec = _tool_spec(registry, name)
        rows.append([name, _tool_detail(name, spec)])
    return rows


def permissions_payload(state: Any) -> list[list[str]]:
    active_tools = [str(name) for name in getattr(state, "active_tools", [])]
    approval_tools = [str(name) for name in getattr(state, "approval_tools", [])]
    high_risk_tools = [
        name
        for name in active_tools
        if classify_tool_risk(name).value in {"high", "critical"}
    ]
    agent_settings = getattr(state.settings, "agent", None)
    mcp_settings = getattr(state.settings, "mcp", None)
    rows = [
        ["profile", str(getattr(state, "permission", "") or "guarded")],
        ["runtime_mode", str(getattr(state, "permission_mode", "") or "auto")],
        ["approval_required", _join_limited(approval_tools) if approval_tools else "none"],
        ["active_tools", str(len(active_tools))],
        ["high_risk_tools", _join_limited(high_risk_tools) if high_risk_tools else "none"],
        ["sandbox_profile", str(getattr(agent_settings, "SANDBOX_PROFILE", "") or "-")],
        ["sandbox_provider", str(getattr(agent_settings, "SANDBOX_PROVIDER", "") or "local")],
        ["sandbox_allowed_commands", _join_limited(_csv_setting(getattr(agent_settings, "SANDBOX_ALLOWED_COMMANDS", "")))],
        ["mcp_execution_mode", str(getattr(mcp_settings, "EXECUTION_MODE", "") or "-")],
    ]
    return rows


async def memory_payload(state: Any) -> list[list[str]]:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not workspace.tenant_id or not workspace.user_id:
        return [["memory", "identity scope not available"]]
    records = await state.persistence.memories.list_for_context(
        workspace.tenant_id,
        workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    if not records:
        return [["memory", "none visible to this session"]]
    rows: list[list[str]] = []
    for record in records[-20:]:
        content = str(record.content).replace("\n", " ")
        if len(content) > 120:
            content = content[:117] + "..."
        rows.append([record.memory_id.replace("mem_", "", 1)[:12], "%s · %s" % (record.scope.value, content)])
    return rows


def _tool_spec(registry: Any, name: str) -> ToolSpec | None:
    if registry is None or not hasattr(registry, "specs"):
        return None
    try:
        specs = list(registry.specs([name]))
    except Exception:
        return None
    return specs[0] if specs else None


def _tool_detail(name: str, spec: ToolSpec | None) -> str:
    metadata = _tool_metadata(spec)
    source = str(metadata.get("source") or _tool_source(name, spec))
    risk = str(metadata.get("risk") or classify_tool_risk(name).value)
    flags = _tool_flags(metadata)
    description = _compact_text(str(getattr(spec, "description", "") or ""))
    parts = ["enabled", source, "risk %s" % risk, flags, description]
    return " · ".join(part for part in parts if part)


def _tool_metadata(spec: ToolSpec | None) -> dict[str, Any]:
    raw = getattr(spec, "raw", None)
    if isinstance(raw, dict) and isinstance(raw.get("metadata"), dict):
        return dict(raw["metadata"])
    return {}


def _tool_source(name: str, spec: ToolSpec | None) -> str:
    if name.startswith("mcp_") or name.startswith("mcp."):
        return "mcp"
    if name.startswith("memory."):
        return "memory"
    if name.startswith("skill."):
        return "skill"
    if name.startswith("tool."):
        return "meta"
    if name.startswith("todo."):
        return "todo"
    if name.startswith("plan."):
        return "plan"
    if name.startswith("task."):
        return "task"
    if name.startswith("agent."):
        return "agent"
    source = str(getattr(spec, "source", "") or "")
    return source if source and source != "registry" else "builtin"


def _tool_flags(metadata: dict[str, Any]) -> str:
    flags = []
    if metadata.get("writes_files"):
        flags.append("writes")
    if metadata.get("writes_state"):
        flags.append("state")
    if metadata.get("requires_process"):
        flags.append("process")
    if metadata.get("requires_network"):
        flags.append("network")
    if metadata.get("spawns_agent"):
        flags.append("agent")
    if metadata.get("model_call"):
        flags.append("model")
    return ", ".join(flags)


def _compact_text(value: str, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _context_layer_counts(items: list[Any]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        layer = getattr(getattr(item, "layer", ""), "value", getattr(item, "layer", ""))
        key = str(layer or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return ", ".join("%s:%s" % (key, value) for key, value in sorted(counts.items())) or "none"


def _safe_len(factory) -> int:
    try:
        return len(factory())
    except Exception:
        return 0


def _catalog_count(rows: list[list[str]], sentinel: str) -> int:
    if len(rows) == 1 and rows[0][0] == sentinel and ("none" in rows[0][1] or "not " in rows[0][1]):
        return 0
    return len(rows)


def _mcp_summary(state: Any) -> str:
    mcp_settings = getattr(state.settings, "mcp", None)
    command = str(getattr(mcp_settings, "SERVER_COMMAND", "") or "").strip()
    if not command:
        return "not configured"
    count = len([name for name in getattr(state, "active_tools", []) if str(name).startswith("mcp_")])
    return "%s · %s tools" % (getattr(mcp_settings, "SERVER_NAME", "") or "default", count)


def _plugin_manifest_row(manifest_path: Path, enabled: set[str] | None = None) -> list[str]:
    plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [plugin_dir.name, "invalid manifest · %s" % exc]
    name = str(raw.get("name") or plugin_dir.name)
    detail = " · ".join(
        part
        for part in [
            "enabled" if enabled and name in enabled else "available",
            str(raw.get("version") or ""),
            str(raw.get("description") or ""),
            str(plugin_dir),
        ]
        if part
    )
    return [name, detail or "available"]


def _agent_profile_detail(profile: Any) -> str:
    spec = dict(getattr(profile, "spec", {}) or {})
    model = dict(spec.get("model", {}) or {})
    tool_permissions = dict(spec.get("tool_permissions", {}) or {})
    parts = [
        str(getattr(profile, "name", "") or ""),
        "model %s/%s" % (model.get("protocol", "") or "-", model.get("model", "") or "-"),
        "permission %s" % (spec.get("permission_profile") or tool_permissions.get("mode") or "auto"),
    ]
    skills = spec.get("skills")
    if skills:
        parts.append("skills %s" % _join_limited([str(skill) for skill in skills], limit=4))
    return " · ".join(part for part in parts if part)


def _task_detail(task: Any) -> str:
    status = getattr(getattr(task, "status", ""), "value", getattr(task, "status", ""))
    title = _compact_text(str(getattr(task, "title", "") or ""), limit=80)
    agent_id = str(getattr(task, "agent_id", "") or "-")
    updated = format_timestamp(float(getattr(task, "updated_at", 0) or 0))
    return " · ".join(part for part in [str(status), "agent %s" % agent_id, updated, title] if part)


def _short_task_id(task_id: str) -> str:
    return str(task_id).replace("task_", "", 1)[:12]


def _join_limited(values: list[str], limit: int = 6) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = " +%s more" % (len(values) - limit) if len(values) > limit else ""
    return ", ".join(shown) + suffix


def session_records_payload(records: list[TerminalSessionRecord]) -> list[dict[str, str]]:
    return [
        {
            "id": record.session_id,
            "short_id": short_session_id(record.session_id),
            "updated": format_timestamp(record.updated_at),
            "model": record.model,
            "messages": str(record.message_count),
            "workspace": short_path(record.workspace_path) if record.workspace_path else "",
        }
        for record in records
    ]


def messages_payload(messages: list[Message]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for message in messages:
        role = str(message.role)
        if role == "system":
            continue
        content = message.content_text()
        if not content and message.tool_calls:
            content = "tool calls: %s" % ", ".join(call.name for call in message.tool_calls)
        if not content:
            continue
        rows.append({"role": role, "content": content})
    return rows


def estimate_session_tokens(session: Any) -> str:
    try:
        return str(session._estimate_tokens(getattr(session, "messages", [])))
    except Exception:
        return "unknown"


def parse_positive_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _csv_setting(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def short_session_id(session_id: str) -> str:
    return str(session_id).replace("session_", "", 1)


def format_timestamp(value: float) -> str:
    if not value:
        return ""
    return datetime.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def model_base_url(session: Any) -> str:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    config = getattr(model_client, "config", None)
    return str(getattr(config, "base_url", "") or "")


def model_endpoint(session: Any) -> str:
    base_url = model_base_url(session)
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    return parsed.netloc or base_url


def short_path(path: str) -> str:
    try:
        value = Path(path).expanduser()
        home = Path.home()
        return "~/%s" % value.relative_to(home) if value.is_relative_to(home) else str(value)
    except Exception:
        return str(path)
