from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.skills import SkillLoader, SkillManifest, SkillRegistry
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.session_state import save_session_state


EXTENSION_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
    },
    "required": ["name"],
}

SKILL_INSTALL_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Local skill JSON file or directory containing skill.json."},
    },
    "required": ["source"],
}

SKILL_UNINSTALL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Installed skill name."},
    },
    "required": ["name"],
}


def skill_install(context: ToolRuntimeContext, source: str) -> dict[str, Any]:
    source_path = _resolve_source(source)
    if not source_path.exists():
        raise FileNotFoundError("skill source not found: %s" % source)
    manifest_path = _skill_manifest_for_source(source_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_name = _safe_file_stem(str(raw.get("name") or manifest_path.stem))
    if not skill_name:
        raise ValueError("skill name is invalid")
    skills_dir = _settings_root(context) / "skills"
    flat_target = skills_dir / ("%s.json" % skill_name)
    package_target = skills_dir / skill_name
    if flat_target.exists() or package_target.exists():
        raise FileExistsError("skill already installed: %s" % skill_name)
    skills_dir.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(source_path, package_target)
        target = package_target / "skill.json"
    else:
        shutil.copy2(source_path, flat_target)
        target = flat_target
    return {"skill": _installed_skill_payload(target, raw), "installed": True}


def skill_uninstall(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    skill_name = _required_text(name, "name")
    enabled = set(getattr(context, "enabled_skills", set()) or set())
    registry = getattr(context, "skill_registry", None)
    if skill_name in enabled or skill_name in set(registry.names() if registry is not None and hasattr(registry, "names") else []):
        raise RuntimeError("disable skill before uninstalling: %s" % skill_name)
    skills_dir = _settings_root(context) / "skills"
    flat = skills_dir / ("%s.json" % skill_name)
    package = skills_dir / skill_name
    if flat.exists():
        flat.unlink()
    elif package.exists():
        shutil.rmtree(package)
    else:
        raise FileNotFoundError("skill not installed: %s" % skill_name)
    return {"skill": skill_name, "uninstalled": True}


async def skill_use(context: ToolRuntimeContext, registry: ToolRegistry, name: str) -> dict[str, Any]:
    skill = _load_skill(context, name)
    _ensure_tools_available(registry, skill.tools, label="skill %s" % skill.name)
    enabled = set(getattr(context, "enabled_skills", set()) or set())
    enabled.add(skill.name)
    context.enabled_skills = enabled
    _add_skill_registry(context, skill)
    _append_prompt(
        context,
        marker="## skills: skill.%s." % skill.name,
        fragments=[
            "## skills: skill.%s.%s\n%s" % (skill.name, index, fragment.strip())
            for index, fragment in enumerate(skill.prompt_fragments)
            if fragment.strip()
        ],
    )
    added_tools = _record_managed_tools(context, "skill_tools", skill.name, skill.tools)
    _add_enabled_tools(context, skill.tools)
    await save_session_state(context)
    return {"skill": _skill_payload(skill), "added_tools": added_tools, "enabled": True}


async def skill_disable(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    skill_name = _required_text(name, "name")
    enabled = set(getattr(context, "enabled_skills", set()) or set())
    if skill_name not in enabled:
        raise RuntimeError("skill is not enabled: %s" % skill_name)
    enabled.remove(skill_name)
    context.enabled_skills = enabled
    removed_tools = _remove_managed_tools(context, "skill_tools", skill_name)
    retained = _managed_tools(context)
    actually_removed = [tool for tool in removed_tools if tool not in retained]
    _remove_enabled_tools(context, actually_removed)
    _remove_skill_registry(context, skill_name)
    await save_session_state(context)
    return {"skill": skill_name, "removed_tools": actually_removed, "enabled": False}


async def plugin_enable(context: ToolRuntimeContext, registry: ToolRegistry, name: str) -> dict[str, Any]:
    manifest = _load_plugin(context, name)
    plugin_name = manifest["name"]
    tools = list(manifest["tools"])
    _ensure_tools_available(registry, tools, label="plugin %s" % plugin_name)
    enabled = set(getattr(context, "enabled_plugins", set()) or set())
    enabled.add(plugin_name)
    context.enabled_plugins = enabled
    _append_prompt(
        context,
        marker="## plugins: plugin.%s." % plugin_name,
        fragments=[
            "## plugins: plugin.%s.%s\n%s" % (plugin_name, index, fragment)
            for index, fragment in enumerate(_plugin_prompt_fragments(manifest))
            if fragment.strip()
        ],
    )
    added_tools = _record_managed_tools(context, "plugin_tools", plugin_name, tools)
    _add_enabled_tools(context, tools)
    await save_session_state(context)
    return {"plugin": _plugin_payload(manifest), "added_tools": added_tools, "enabled": True}


async def plugin_disable(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    plugin_name = _required_text(name, "name")
    enabled = set(getattr(context, "enabled_plugins", set()) or set())
    if plugin_name not in enabled:
        raise RuntimeError("plugin is not enabled: %s" % plugin_name)
    enabled.remove(plugin_name)
    context.enabled_plugins = enabled
    removed_tools = _remove_managed_tools(context, "plugin_tools", plugin_name)
    retained = _managed_tools(context)
    actually_removed = [tool for tool in removed_tools if tool not in retained]
    _remove_enabled_tools(context, actually_removed)
    await save_session_state(context)
    return {"plugin": plugin_name, "removed_tools": actually_removed, "enabled": False}


def _load_skill(context: ToolRuntimeContext, name: str) -> SkillManifest:
    root = _settings_root(context)
    return SkillLoader(root).load(_required_text(name, "name"))


def _settings_root(context: ToolRuntimeContext) -> Path:
    root = getattr(getattr(context.settings, "server", None), "ROOT_PATH", "") if context.settings is not None else ""
    return Path(str(root or context.workspace.path))


def _resolve_source(source: str) -> Path:
    value = str(source or "").strip()
    if not value:
        raise ValueError("source is required")
    return Path(value).expanduser().resolve()


def _skill_manifest_for_source(path: Path) -> Path:
    if path.is_dir():
        candidate = path / "skill.json"
        if not candidate.exists():
            raise FileNotFoundError("skill.json not found in: %s" % path)
        return candidate
    if path.is_file():
        return path
    raise FileNotFoundError("skill source not found: %s" % path)


def _installed_skill_payload(path: Path, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(raw.get("name") or path.stem),
        "version": str(raw.get("version") or "0.1.0"),
        "description": str(raw.get("description") or ""),
        "tools": [str(tool) for tool in raw.get("tools", [])],
        "prompt_fragments": [str(item) for item in raw.get("prompt_fragments", [])],
        "path": str(path),
    }


def _add_skill_registry(context: ToolRuntimeContext, skill: SkillManifest) -> None:
    registry = getattr(context, "skill_registry", None)
    if registry is None:
        registry = SkillRegistry([])
        context.skill_registry = registry
    registry.skills = [item for item in list(registry.skills) if item.name != skill.name] + [skill]


def _remove_skill_registry(context: ToolRuntimeContext, name: str) -> None:
    registry = getattr(context, "skill_registry", None)
    if registry is not None:
        registry.skills = [item for item in list(registry.skills) if item.name != name]


def _load_plugin(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    wanted = _required_text(name, "name")
    root = Path(context.workspace.path)
    for manifest_path in _plugin_manifest_paths(root):
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
        plugin_name = str(raw.get("name") or plugin_dir.name)
        if wanted not in {plugin_name, plugin_dir.name}:
            continue
        return {
            "name": plugin_name,
            "version": str(raw.get("version") or ""),
            "description": str(raw.get("description") or ""),
            "tools": [str(tool) for tool in raw.get("tools", []) if str(tool)],
            "prompt_fragments": [str(item) for item in raw.get("prompt_fragments", [])],
            "path": str(plugin_dir),
            "raw": raw,
        }
    raise FileNotFoundError("plugin not found: %s" % wanted)


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_prompt_fragments(manifest: dict[str, Any]) -> list[str]:
    root = Path(str(manifest["path"])).resolve()
    fragments: list[str] = []
    for relative_path in manifest.get("prompt_fragments", []) or []:
        path = (root / str(relative_path)).resolve()
        if not _is_relative_to(path, root):
            raise PermissionError("plugin prompt path escapes plugin root: %s" % relative_path)
        fragments.append(path.read_text(encoding="utf-8").strip())
    return fragments


def _append_prompt(context: ToolRuntimeContext, *, marker: str, fragments: list[str]) -> None:
    if not fragments:
        return
    session = getattr(context, "session", None)
    if session is None:
        raise RuntimeError("session is not available")
    prompt = str(getattr(session, "system_prompt", "") or "")
    if marker in prompt:
        return
    next_prompt = "%s\n\n%s" % (prompt, "\n\n".join(fragments)) if prompt else "\n\n".join(fragments)
    set_prompt = getattr(session, "set_system_prompt", None)
    if set_prompt is not None:
        set_prompt(next_prompt.strip())
    else:
        session.system_prompt = next_prompt.strip()


def _ensure_tools_available(registry: ToolRegistry, tools: list[str], *, label: str) -> None:
    available = set(registry.names())
    missing = [tool for tool in tools if tool not in available]
    if missing:
        raise RuntimeError("%s references unavailable tools: %s" % (label, ", ".join(missing)))


def _record_managed_tools(context: ToolRuntimeContext, mapping_name: str, name: str, tools: list[str]) -> list[str]:
    current_tools = set(getattr(context, "enabled_tools", []) or [])
    mapping = dict(getattr(context, mapping_name, {}) or {})
    added_tools = [tool for tool in tools if tool not in current_tools]
    mapping[name] = added_tools
    setattr(context, mapping_name, mapping)
    return added_tools


def _remove_managed_tools(context: ToolRuntimeContext, mapping_name: str, name: str) -> list[str]:
    mapping = dict(getattr(context, mapping_name, {}) or {})
    removed = list(mapping.pop(name, []) or [])
    setattr(context, mapping_name, mapping)
    return removed


def _managed_tools(context: ToolRuntimeContext) -> set[str]:
    tools: set[str] = set()
    for mapping_name in ["plugin_tools", "skill_tools"]:
        for group in dict(getattr(context, mapping_name, {}) or {}).values():
            tools.update(group)
    return tools


def _add_enabled_tools(context: ToolRuntimeContext, tools: list[str]) -> None:
    context.enabled_tools = _merge_unique(list(getattr(context, "enabled_tools", []) or []), tools)
    runtime = getattr(getattr(context, "session", None), "runtime", None)
    config = getattr(runtime, "config", None)
    if config is not None:
        runtime.config = replace(config, enabled_tools=_merge_unique(list(getattr(config, "enabled_tools", []) or []), tools))


def _remove_enabled_tools(context: ToolRuntimeContext, tools: list[str]) -> None:
    removed = set(tools)
    context.enabled_tools = [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed]
    runtime = getattr(getattr(context, "session", None), "runtime", None)
    config = getattr(runtime, "config", None)
    if config is not None:
        runtime.config = replace(config, enabled_tools=[tool for tool in list(getattr(config, "enabled_tools", []) or []) if tool not in removed])


def _merge_unique(*groups: list[str]) -> list[str]:
    names: list[str] = []
    seen = set()
    for group in groups:
        for name in group:
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _skill_payload(skill: SkillManifest) -> dict[str, Any]:
    return {
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "tools": list(skill.tools),
        "paths": list(getattr(skill, "path_patterns", []) or []),
        "prompt_fragments": len(skill.prompt_fragments),
    }


def _plugin_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "tools": list(manifest["tools"]),
        "prompt_fragments": list(manifest["prompt_fragments"]),
        "path": manifest["path"],
    }


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _safe_file_stem(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/").split("/")[-1]
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in text)
    return safe.strip(".-")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
