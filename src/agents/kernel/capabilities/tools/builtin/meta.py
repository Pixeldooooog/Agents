from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.skills import coerce_path_patterns
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


TOOL_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Tool name or keyword query. Use select:<tool> for exact lookup."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
        "include_all": {"type": "boolean", "description": "Include registered tools that are not enabled for this session."},
    },
}

SRC_ORIGIN_TOOL_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Deferred tool name or keyword query."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["query"],
    "additionalProperties": False,
}

SKILL_DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Skill name, description, or tool keyword query."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
        "include_prompt": {"type": "boolean", "description": "Include prompt fragment file names from the manifest."},
    },
}


async def tool_search(
    context: ToolRuntimeContext,
    registry: ToolRegistry,
    query: str = "",
    max_results: int = 20,
    include_all: bool = False,
) -> dict[str, Any]:
    enabled = set(getattr(context, "enabled_tools", []) or [])
    specs = registry.specs()
    if not include_all and enabled:
        specs = [spec for spec in specs if spec.name in enabled]
    matches = _ranked_tool_matches(specs, query=query, max_results=max_results, enabled=enabled)
    return {
        "query": str(query or ""),
        "matches": matches,
        "count": len(matches),
        "total_registered_tools": len(registry.names()),
        "total_enabled_tools": len(enabled),
    }


async def src_origin_tool_search(
    _context: ToolRuntimeContext,
    registry: ToolRegistry,
    query: str,
    max_results: int = 5,
) -> dict[str, Any]:
    specs = registry.specs()
    deferred_specs = [spec for spec in specs if _metadata(spec).get("defer") is True]
    return {
        "query": str(query or ""),
        "matches": _src_origin_tool_matches(specs, deferred_specs, query=query, max_results=max_results),
        "total_deferred_tools": len(deferred_specs),
    }


def format_src_origin_tool_search_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    matches = [str(name) for name in result.get("matches") or []]
    if matches:
        return "\n".join(matches)
    pending_servers = [str(server) for server in result.get("pending_mcp_servers") or []]
    if pending_servers:
        return "No matching deferred tools found\nPending MCP servers: " + ", ".join(pending_servers)
    return "No matching deferred tools found"


async def skill_discover(
    context: ToolRuntimeContext,
    query: str = "",
    max_results: int = 20,
    include_prompt: bool = False,
) -> dict[str, Any]:
    manifests = _skill_manifests(context, include_prompt=include_prompt)
    matches = _ranked_skill_matches(manifests, query=query, max_results=max_results)
    return {
        "query": str(query or ""),
        "skills": matches,
        "count": len(matches),
        "total_available_skills": len(manifests),
        "enabled_skills": _enabled_skill_names(context),
    }


def _ranked_tool_matches(specs: list[Any], *, query: str, max_results: int, enabled: set[str]) -> list[dict[str, Any]]:
    selected = []
    terms = _query_terms(query)
    exact = _select_exact(query)
    for spec in specs:
        metadata = _metadata(spec)
        haystack = " ".join([spec.name, str(getattr(spec, "description", "") or ""), json.dumps(metadata, sort_keys=True)])
        score = _score(spec.name, haystack, terms, exact)
        if terms or exact:
            if score <= 0:
                continue
        selected.append((score, spec.name, spec, metadata))
    selected.sort(key=lambda item: (-item[0], item[1]))
    limit = _limit(max_results)
    return [
        {
            "name": spec.name,
            "description": str(getattr(spec, "description", "") or ""),
            "enabled": spec.name in enabled,
            "metadata": metadata,
        }
        for _, _, spec, metadata in selected[:limit]
    ]


def _ranked_skill_matches(manifests: list[dict[str, Any]], *, query: str, max_results: int) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    exact = _select_exact(query)
    selected = []
    for manifest in manifests:
        haystack = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        score = _score(str(manifest.get("name") or ""), haystack, terms, exact)
        if terms or exact:
            if score <= 0:
                continue
        selected.append((score, str(manifest.get("name") or ""), manifest))
    selected.sort(key=lambda item: (-item[0], item[1]))
    return [manifest for _, _, manifest in selected[: _limit(max_results)]]


def _src_origin_tool_matches(
    specs: list[Any],
    deferred_specs: list[Any],
    *,
    query: str,
    max_results: int,
) -> list[str]:
    selected_names = _select_names(query)
    if selected_names:
        return _select_tool_names([*deferred_specs, *specs], selected_names, max_results=max_results)
    return [
        match["name"]
        for match in _ranked_tool_matches(deferred_specs, query=query, max_results=max_results, enabled=set())
    ]


def _select_tool_names(specs: list[Any], names: list[str], *, max_results: int) -> list[str]:
    lookup: dict[str, str] = {}
    for spec in specs:
        lookup.setdefault(spec.name.lower(), spec.name)
    selected: list[str] = []
    seen: set[str] = set()
    for name in names:
        match = lookup.get(name.lower())
        if match is None or match in seen:
            continue
        selected.append(match)
        seen.add(match)
        if len(selected) >= _limit(max_results):
            break
    return selected


def _skill_manifests(context: ToolRuntimeContext, *, include_prompt: bool) -> list[dict[str, Any]]:
    root = _settings_root(context)
    enabled = set(_enabled_skill_names(context))
    manifests: list[dict[str, Any]] = []
    skills_dir = root / "skills"
    for manifest_path in _skill_manifest_paths(skills_dir):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - invalid manifests should be visible to the model.
            name = manifest_path.parent.name if manifest_path.name == "skill.json" else manifest_path.stem
            manifests.append({"name": name, "enabled": name in enabled, "error": str(exc)})
            continue
        default_name = manifest_path.parent.name if manifest_path.name == "skill.json" else manifest_path.stem
        name = str(raw.get("name") or default_name)
        payload = {
            "name": name,
            "version": str(raw.get("version") or "0.1.0"),
            "description": str(raw.get("description") or ""),
            "enabled": name in enabled,
            "dependencies": list(raw.get("dependencies", raw.get("requires", [])) or []),
            "tools": list(raw.get("tools") or []),
            "paths": _manifest_path_patterns(raw),
            "metadata": dict(raw.get("metadata") or {}),
        }
        if include_prompt:
            payload["prompt_fragments"] = list(raw.get("prompt_fragments") or [])
        manifests.append(payload)
    for skill in getattr(getattr(context, "skill_registry", None), "skills", []) or []:
        if any(item.get("name") == skill.name for item in manifests):
            continue
        manifests.append(
            {
                "name": skill.name,
                "version": skill.version,
                "description": skill.description,
                "enabled": True,
                "dependencies": list(skill.dependencies),
                "tools": list(skill.tools),
                "paths": list(getattr(skill, "path_patterns", []) or []),
                "metadata": dict(skill.metadata),
            }
        )
    return manifests


def _skill_manifest_paths(skills_dir: Path) -> list[Path]:
    if not skills_dir.exists():
        return []
    return sorted([*skills_dir.glob("*.json"), *skills_dir.glob("*/skill.json")])


def _settings_root(context: ToolRuntimeContext) -> Path:
    settings = getattr(context, "settings", None)
    root = getattr(getattr(settings, "server", None), "ROOT_PATH", "") if settings is not None else ""
    return Path(root or context.workspace.root or context.workspace.path).expanduser()


def _enabled_skill_names(context: ToolRuntimeContext) -> list[str]:
    registry = getattr(context, "skill_registry", None)
    names = getattr(registry, "names", None)
    if callable(names):
        return list(names())
    return []


def _metadata(spec: Any) -> dict[str, Any]:
    raw = getattr(spec, "raw", None)
    if isinstance(raw, dict) and isinstance(raw.get("metadata"), dict):
        return dict(raw["metadata"])
    return {}


def _manifest_path_patterns(raw: dict[str, Any]) -> list[str]:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return coerce_path_patterns(raw.get("paths", metadata.get("paths")))


def _score(name: str, haystack: str, terms: list[str], exact: str) -> int:
    text = haystack.lower()
    lowered_name = name.lower()
    if exact:
        return 1000 if lowered_name == exact or lowered_name.endswith(exact) else 0
    if not terms:
        return 1
    score = 0
    for term in terms:
        if term == lowered_name:
            score += 100
        elif term in lowered_name:
            score += 25
        elif term in text:
            score += 5
    return score


def _query_terms(query: str) -> list[str]:
    value = str(query or "").strip().lower()
    if value.startswith("select:"):
        return []
    return [term for term in value.replace(".", " ").replace("_", " ").replace("-", " ").split() if term]


def _select_exact(query: str) -> str:
    value = str(query or "").strip().lower()
    return value.removeprefix("select:").strip() if value.startswith("select:") else ""


def _select_names(query: str) -> list[str]:
    value = str(query or "").strip()
    if not value.lower().startswith("select:"):
        return []
    selected = value.split(":", 1)[1]
    return [name.strip() for name in selected.split(",") if name.strip()]


def _limit(value: int) -> int:
    return max(1, min(int(value or 20), 50))
