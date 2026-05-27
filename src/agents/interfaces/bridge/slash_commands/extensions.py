from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agents.interfaces.bridge.payloads import plugins_payload, skills_payload, tools_payload
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    merge_unique,
    remove_runtime_enabled_tools,
    replace_runtime_enabled_tools,
    safe_file_stem,
    set_session_prompt,
    split_once,
    tool_context,
)
from agents.interfaces.bridge.slash_commands.permissions import sync_permission_state_from_context
from agents.interfaces.bridge.slash_commands.tool_execution import execute_slash_tool
from agents.kernel.capabilities.skills import SkillLoader
from agents.kernel.capabilities.tools.builtin.extensions import skill_install, skill_uninstall
from agents.kernel.capabilities.tools.builtin.plugins import plugin_install, plugin_uninstall
from agents.kernel.context import ContextLayer, ContextTraceItem
from agents.kernel.session_state import save_session_state


async def handle_skills_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action:
        write({"type": "skills", "skills": skills_payload(state)})
        return
    if action in {"use", "enable"}:
        await _handle_skill_use(state, rest, write=write)
        return
    if action in {"disable", "remove"}:
        await _handle_skill_disable(state, rest, write=write)
        return
    if action == "install":
        await _handle_skill_install(state, rest, write=write)
        return
    if action in {"uninstall", "delete"}:
        await _handle_skill_uninstall(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown skills command: %s" % action})


async def handle_plugins_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action:
        write({"type": "plugins", "plugins": plugins_payload(state)})
        return
    if action in {"enable", "use"}:
        await _handle_plugin_enable(state, rest, write=write)
        return
    if action in {"disable", "remove"}:
        await _handle_plugin_disable(state, rest, write=write)
        return
    if action == "install":
        await _handle_plugin_install(state, rest, write=write)
        return
    if action in {"uninstall", "delete"}:
        await _handle_plugin_uninstall(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown plugins command: %s" % action})


def sync_extension_state_from_context(state: Any) -> None:
    context = tool_context(state)
    if context is None:
        return
    state.enabled_skills = set(getattr(context, "enabled_skills", set()) or set())
    state.enabled_plugins = set(getattr(context, "enabled_plugins", set()) or set())
    state.skill_tools = dict(getattr(context, "skill_tools", {}) or {})
    state.plugin_tools = dict(getattr(context, "plugin_tools", {}) or {})
    if bool(getattr(context, "permission_overridden", False)):
        sync_permission_state_from_context(state)


async def _handle_skill_use(state: Any, name: str, *, write: BridgeWriter) -> None:
    skill_name = name.strip()
    if not skill_name:
        write({"type": "error", "message": "usage: /skills use <name>"})
        return
    try:
        skill = SkillLoader(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).load(skill_name)
    except Exception as exc:
        write({"type": "error", "message": "failed to load skill %s: %s" % (skill_name, exc)})
        return
    missing_tools = _missing_skill_tools(state, skill.tools)
    if missing_tools:
        write({"type": "error", "message": "skill %s references unavailable tools: %s" % (skill.name, ", ".join(missing_tools))})
        return
    enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    enabled_skills.add(skill.name)
    state.enabled_skills = enabled_skills
    _append_skill_prompt(state.session, skill.name, skill.prompt_fragments)
    skill_tools = dict(getattr(state, "skill_tools", {}) or {})
    skill_tools[skill.name] = [tool for tool in skill.tools if tool not in set(getattr(state, "active_tools", []) or [])]
    state.skill_tools = skill_tools
    state.active_tools = merge_unique(list(getattr(state, "active_tools", []) or []), skill.tools)
    replace_runtime_enabled_tools(state, skill.tools)
    await _persist_extension_state(state)
    write({"type": "notice", "message": "skill enabled: %s" % skill.name})
    write({"type": "skills", "skills": skills_payload(state)})


async def _handle_skill_disable(state: Any, name: str, *, write: BridgeWriter) -> None:
    skill_name = name.strip()
    if not skill_name:
        write({"type": "error", "message": "usage: /skills disable <name>"})
        return
    enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    if skill_name not in enabled_skills:
        write({"type": "error", "message": "skill is not enabled: %s" % skill_name})
        return
    enabled_skills.remove(skill_name)
    state.enabled_skills = enabled_skills
    skill_tools = dict(getattr(state, "skill_tools", {}) or {})
    removed_tools = list(skill_tools.pop(skill_name, []) or [])
    state.skill_tools = skill_tools
    retained_tools = _managed_tools_except(state, removed_tools)
    state.active_tools = [
        tool
        for tool in list(getattr(state, "active_tools", []) or [])
        if tool not in removed_tools or tool in retained_tools
    ]
    remove_runtime_enabled_tools(state, [tool for tool in removed_tools if tool not in retained_tools])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "skill disabled: %s" % skill_name})
    write({"type": "skills", "skills": skills_payload(state)})
    if removed_tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_skill_install(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not rest.strip():
        write({"type": "error", "message": "usage: /skills install <local_skill_json_or_dir>"})
        return
    payload = await execute_slash_tool(
        state,
        tool_name="skill.install",
        arguments={"source": rest.strip()},
        write=write,
        error_label="skill install",
        fallback=lambda: skill_install(context, source=rest.strip()),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "skill installed: %s" % payload["skill"]["name"]})
    write({"type": "skills", "skills": skills_payload(state)})


async def _handle_skill_uninstall(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not rest.strip():
        write({"type": "error", "message": "usage: /skills uninstall <name>"})
        return
    payload = await execute_slash_tool(
        state,
        tool_name="skill.uninstall",
        arguments={"name": rest.strip()},
        write=write,
        error_label="skill uninstall",
        fallback=lambda: skill_uninstall(context, name=rest.strip()),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "skill uninstalled: %s" % payload["skill"]})
    write({"type": "skills", "skills": skills_payload(state)})


async def _handle_plugin_enable(state: Any, name: str, *, write: BridgeWriter) -> None:
    plugin_name = name.strip()
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins enable <name>"})
        return
    manifest = _load_plugin_manifest(state, plugin_name)
    if manifest is None:
        write({"type": "error", "message": "plugin not found: %s" % plugin_name})
        return
    resolved_name = str(manifest["raw"].get("name") or manifest["path"].parent.name)
    tools = [str(tool) for tool in manifest["raw"].get("tools", []) if str(tool)]
    missing_tools = _missing_skill_tools(state, tools)
    if missing_tools:
        write({"type": "error", "message": "plugin %s references unavailable tools: %s" % (resolved_name, ", ".join(missing_tools))})
        return
    enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    enabled_plugins.add(resolved_name)
    state.enabled_plugins = enabled_plugins
    plugin_tools = dict(getattr(state, "plugin_tools", {}) or {})
    plugin_tools[resolved_name] = [tool for tool in tools if tool not in set(getattr(state, "active_tools", []) or [])]
    state.plugin_tools = plugin_tools
    state.active_tools = merge_unique(list(getattr(state, "active_tools", []) or []), tools)
    replace_runtime_enabled_tools(state, tools)
    _append_plugin_prompt(state.session, resolved_name, manifest["raw"], manifest["plugin_dir"])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "plugin enabled: %s" % resolved_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})
    if tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_plugin_disable(state: Any, name: str, *, write: BridgeWriter) -> None:
    plugin_name = name.strip()
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins disable <name>"})
        return
    enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    if plugin_name not in enabled_plugins:
        write({"type": "error", "message": "plugin is not enabled: %s" % plugin_name})
        return
    enabled_plugins.remove(plugin_name)
    state.enabled_plugins = enabled_plugins
    plugin_tools = dict(getattr(state, "plugin_tools", {}) or {})
    removed_tools = list(plugin_tools.pop(plugin_name, []) or [])
    state.plugin_tools = plugin_tools
    retained_plugin_tools = _managed_tools_except(state, removed_tools)
    state.active_tools = [
        tool
        for tool in list(getattr(state, "active_tools", []) or [])
        if tool not in removed_tools or tool in retained_plugin_tools
    ]
    remove_runtime_enabled_tools(state, [tool for tool in removed_tools if tool not in retained_plugin_tools])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "plugin disabled: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})
    if removed_tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_plugin_install(state: Any, rest: str, *, write: BridgeWriter) -> None:
    source = Path(rest.strip()).expanduser()
    if not rest.strip():
        write({"type": "error", "message": "usage: /plugins install <local_plugin_dir>"})
        return
    context = tool_context(state)
    payload = await execute_slash_tool(
        state,
        tool_name="plugin.install",
        arguments={"source": str(source)},
        write=write,
        error_label="plugin install",
        fallback=(lambda: plugin_install(context, source=str(source)))
        if context is not None
        else (lambda: _plugin_install_local(state, source)),
    )
    if payload is None:
        return
    plugin = dict(payload.get("plugin") or {})
    plugin_name = str(plugin.get("name") or source.name)
    write({"type": "notice", "message": "plugin installed: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})


async def _handle_plugin_uninstall(state: Any, rest: str, *, write: BridgeWriter) -> None:
    plugin_name = safe_file_stem(rest.strip())
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins uninstall <name>"})
        return
    context = tool_context(state)
    payload = await execute_slash_tool(
        state,
        tool_name="plugin.uninstall",
        arguments={"name": plugin_name},
        write=write,
        error_label="plugin uninstall",
        fallback=(lambda: plugin_uninstall(context, name=plugin_name))
        if context is not None
        else (lambda: _plugin_uninstall_local(state, plugin_name)),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "plugin uninstalled: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})


def _append_skill_prompt(session: Any, skill_name: str, fragments: list[str]) -> None:
    prompt = str(getattr(session, "system_prompt", "") or "")
    marker = "## skills: skill.%s." % skill_name
    if marker in prompt:
        return
    rendered = "\n\n".join(
        "## skills: skill.%s.%s\n%s" % (skill_name, index, fragment.strip())
        for index, fragment in enumerate(fragments)
        if fragment.strip()
    )
    if rendered:
        set_session_prompt(session, "\n\n".join(part for part in [prompt, rendered] if part.strip()))
    trace = list(getattr(session, "context_trace", []) or [])
    for index, fragment in enumerate(fragments):
        text = fragment.strip()
        if text:
            trace.append(
                ContextTraceItem(
                    id="skill.%s.%s" % (skill_name, index),
                    layer=ContextLayer.SKILLS,
                    source="skill:%s" % skill_name,
                    tokens=max(1, len(text.encode("utf-8")) // 4),
                    included=True,
                )
            )
    if hasattr(session, "context_trace"):
        session.context_trace = trace


def _append_plugin_prompt(session: Any, plugin_name: str, raw: dict[str, Any], plugin_dir: Path) -> None:
    fragments: list[str] = []
    prompt = str(raw.get("prompt") or "").strip()
    if prompt:
        fragments.append(prompt)
    for relative_path in raw.get("prompt_fragments", []) or []:
        try:
            text = (plugin_dir / str(relative_path)).read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            fragments.append(text)
    if not fragments:
        return
    current = str(getattr(session, "system_prompt", "") or "")
    marker = "## plugins: plugin.%s." % plugin_name
    if marker in current:
        return
    rendered = "\n\n".join(
        "## plugins: plugin.%s.%s\n%s" % (plugin_name, index, fragment)
        for index, fragment in enumerate(fragments)
    )
    set_session_prompt(session, "\n\n".join(part for part in [current, rendered] if part.strip()))


def _missing_skill_tools(state: Any, tools: list[str]) -> list[str]:
    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    if registry is None or not hasattr(registry, "names"):
        return list(tools)
    available = set(registry.names())
    return [tool for tool in tools if tool not in available]


def _load_plugin_manifest(state: Any, name: str) -> dict[str, Any] | None:
    root = Path(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).expanduser()
    for manifest_path in _plugin_manifest_paths(root):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
        plugin_name = str(raw.get("name") or plugin_dir.name)
        if name in {plugin_name, plugin_dir.name}:
            return {"raw": raw, "path": manifest_path, "plugin_dir": plugin_dir}
    return None


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_install_local(state: Any, source: Path) -> dict[str, Any]:
    source_dir = Path(source).expanduser()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError("plugin source not found: %s" % source)
    manifest_path = _plugin_manifest_for_dir(source_dir)
    if manifest_path is None:
        raise FileNotFoundError("plugin manifest not found in: %s" % source_dir)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    plugin_name = safe_file_stem(str(raw.get("name") or source_dir.name))
    if not plugin_name:
        raise ValueError("plugin name is invalid")
    target = _plugin_install_root(state) / plugin_name
    if target.exists():
        raise FileExistsError("plugin already installed: %s" % plugin_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target)
    return {
        "plugin": {
            "name": plugin_name,
            "description": str(raw.get("description") or ""),
            "version": str(raw.get("version") or ""),
            "path": str(target),
        },
        "installed": True,
    }


def _plugin_uninstall_local(state: Any, plugin_name: str) -> dict[str, Any]:
    if plugin_name in set(getattr(state, "enabled_plugins", set()) or set()):
        raise RuntimeError("disable plugin before uninstalling: %s" % plugin_name)
    target = _plugin_install_root(state) / plugin_name
    if not target.exists():
        raise FileNotFoundError("plugin not installed: %s" % plugin_name)
    shutil.rmtree(target)
    return {"plugin": plugin_name, "uninstalled": True}


def _plugin_install_root(state: Any) -> Path:
    root = Path(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).expanduser()
    return root / ".agents" / "plugins"


def _plugin_manifest_for_dir(path: Path) -> Path | None:
    candidates = [path / ".codex-plugin" / "plugin.json", path / "plugin.json"]
    return next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)


def _managed_tools_except(state: Any, excluded: list[str]) -> set[str]:
    managed: set[str] = set()
    for mapping_name in ["plugin_tools", "skill_tools"]:
        mapping = dict(getattr(state, mapping_name, {}) or {})
        for group in mapping.values():
            for tool in group:
                managed.add(tool)
    return managed


async def _persist_extension_state(state: Any) -> None:
    context = tool_context(state)
    if context is None:
        return
    context.enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    context.enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    context.skill_tools = {
        str(name): [str(tool) for tool in tools]
        for name, tools in dict(getattr(state, "skill_tools", {}) or {}).items()
    }
    context.plugin_tools = {
        str(name): [str(tool) for tool in tools]
        for name, tools in dict(getattr(state, "plugin_tools", {}) or {}).items()
    }
    await save_session_state(context)
