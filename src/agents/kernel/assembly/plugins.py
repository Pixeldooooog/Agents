from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.kernel.context.pack import ContextFragment, ContextLayer, ContextScope

from agents.kernel.assembly.common import merge_unique


def managed_extension_tools(tool_context: Any) -> list[str]:
    groups: list[list[str]] = []
    for mapping_name in ("skill_tools", "plugin_tools"):
        mapping = dict(getattr(tool_context, mapping_name, {}) or {})
        groups.extend([list(tools or []) for tools in mapping.values()])
    return merge_unique(*groups)


def plugin_enabled_tools(settings: Any, tool_context: Any) -> list[str]:
    enabled = sorted({str(name) for name in getattr(tool_context, "enabled_plugins", set()) or set() if str(name)})
    if not enabled:
        return []
    manifests = plugin_manifests(settings, tool_context)
    groups = []
    for plugin_name in enabled:
        manifest = manifests.get(plugin_name)
        if manifest is None:
            continue
        raw = dict(manifest.get("raw") or {})
        groups.append([str(tool) for tool in raw.get("tools", []) or [] if str(tool)])
    return merge_unique(*groups)


def plugin_context_fragments(settings: Any, tool_context: Any) -> list[ContextFragment]:
    fragments: list[ContextFragment] = []
    enabled = sorted({str(name) for name in getattr(tool_context, "enabled_plugins", set()) or set() if str(name)})
    if not enabled:
        return fragments
    manifests = plugin_manifests(settings, tool_context)
    for plugin_name in enabled:
        manifest = manifests.get(plugin_name)
        if manifest is None:
            continue
        for index, text in enumerate(_plugin_prompt_fragments(manifest)):
            if not text.strip():
                continue
            fragments.append(
                ContextFragment(
                    id="plugin.%s.%s" % (plugin_name, index),
                    layer=ContextLayer.SKILLS,
                    text=text.strip(),
                    source="plugin:%s" % plugin_name,
                    priority=55,
                    scope=ContextScope.SESSION,
                )
            )
    return fragments


def plugin_manifests(settings: Any, tool_context: Any) -> dict[str, dict[str, Any]]:
    roots = _unique_paths(
        [
            getattr(tool_context.workspace, "path", ""),
            getattr(getattr(settings, "server", None), "ROOT_PATH", ""),
        ]
    )
    manifests: dict[str, dict[str, Any]] = {}
    for root in roots:
        for manifest_path in _plugin_manifest_paths(root):
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
            plugin_name = str(raw.get("name") or plugin_dir.name)
            manifests.setdefault(plugin_name, {"raw": raw, "path": manifest_path, "plugin_dir": plugin_dir})
    return manifests


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_prompt_fragments(manifest: dict[str, Any]) -> list[str]:
    raw = dict(manifest.get("raw") or {})
    plugin_dir = Path(manifest["plugin_dir"]).resolve()
    fragments = [str(raw.get("prompt") or "").strip()]
    for relative_path in raw.get("prompt_fragments", []) or []:
        path = (plugin_dir / str(relative_path)).resolve()
        if not _is_relative_to(path, plugin_dir):
            continue
        try:
            fragments.append(path.read_text(encoding="utf-8").strip())
        except Exception:
            continue
    return [fragment for fragment in fragments if fragment]


def _unique_paths(values: list[Any]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if not value:
            continue
        path = Path(str(value)).expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
