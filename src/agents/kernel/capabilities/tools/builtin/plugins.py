from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


PLUGIN_DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional text filter over plugin name, description, and tools."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
        "include_prompt": {"type": "boolean", "description": "Include prompt fragment contents when true."},
    },
}

PLUGIN_INSTALL_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Local plugin directory to copy into .agents/plugins."},
    },
    "required": ["source"],
}

PLUGIN_UNINSTALL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Installed plugin name."},
    },
    "required": ["name"],
}


async def plugin_discover(
    context: ToolRuntimeContext,
    query: str = "",
    max_results: int = 20,
    include_prompt: bool = False,
) -> dict[str, Any]:
    plugins = _discover_plugins(context)
    needle = str(query or "").strip().lower()
    matches = [plugin for plugin in plugins if _matches(plugin, needle)] if needle else plugins
    limit = max(1, min(int(max_results or 20), 100))
    return {
        "plugins": [_plugin_payload(plugin, include_prompt=bool(include_prompt)) for plugin in matches[:limit]],
        "count": min(len(matches), limit),
        "total_available_plugins": len(plugins),
    }


def plugin_install(context: ToolRuntimeContext, source: str) -> dict[str, Any]:
    source_path = _resolve_source(source)
    if not source_path.exists() or not source_path.is_dir():
        raise FileNotFoundError("plugin source not found: %s" % source)
    manifest_path = _plugin_manifest_for_dir(source_path)
    if manifest_path is None:
        raise FileNotFoundError("plugin manifest not found in: %s" % source_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    plugin_name = _safe_file_stem(str(raw.get("name") or source_path.name))
    if not plugin_name:
        raise ValueError("plugin name is invalid")
    target = _install_root(context) / plugin_name
    if target.exists():
        raise FileExistsError("plugin already installed: %s" % plugin_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_path, target)
    return {"plugin": _installed_plugin_payload(target, raw), "installed": True}


def plugin_uninstall(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    plugin_name = _safe_file_stem(str(name or ""))
    if not plugin_name:
        raise ValueError("name is required")
    if plugin_name in set(getattr(context, "enabled_plugins", set()) or set()):
        raise RuntimeError("disable plugin before uninstalling: %s" % plugin_name)
    target = _install_root(context) / plugin_name
    if not target.exists():
        raise FileNotFoundError("plugin not installed: %s" % plugin_name)
    shutil.rmtree(target)
    return {"plugin": plugin_name, "uninstalled": True}


def _discover_plugins(context: ToolRuntimeContext) -> list[dict[str, Any]]:
    root = Path(context.workspace.path)
    manifests: list[dict[str, Any]] = []
    for manifest_path in _plugin_manifest_paths(root):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - plugin catalog should surface bad manifests.
            manifests.append(
                {
                    "name": _plugin_dir(manifest_path).name,
                    "version": "",
                    "description": "invalid manifest: %s" % exc,
                    "path": str(_plugin_dir(manifest_path)),
                    "manifest_path": str(manifest_path),
                    "tools": [],
                    "prompt_fragments": [],
                    "metadata": {},
                    "invalid": True,
                }
            )
            continue
        plugin_dir = _plugin_dir(manifest_path)
        manifests.append(
            {
                "name": str(raw.get("name") or plugin_dir.name),
                "version": str(raw.get("version") or ""),
                "description": str(raw.get("description") or ""),
                "path": str(plugin_dir),
                "manifest_path": str(manifest_path),
                "tools": [str(item) for item in raw.get("tools", [])],
                "prompt_fragments": [str(item) for item in raw.get("prompt_fragments", [])],
                "metadata": dict(raw.get("metadata", {})),
                "invalid": False,
            }
        )
    return sorted(manifests, key=lambda item: str(item["name"]))


def _resolve_source(source: str) -> Path:
    value = str(source or "").strip()
    if not value:
        raise ValueError("source is required")
    return Path(value).expanduser().resolve()


def _install_root(context: ToolRuntimeContext) -> Path:
    return Path(context.workspace.path).resolve() / ".agents" / "plugins"


def _plugin_manifest_for_dir(path: Path) -> Path | None:
    candidates = [path / ".codex-plugin" / "plugin.json", path / "plugin.json"]
    return next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_dir(manifest_path: Path) -> Path:
    return manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent


def _installed_plugin_payload(path: Path, raw: dict[str, Any]) -> dict[str, Any]:
    manifest_path = _plugin_manifest_for_dir(path)
    return {
        "name": str(raw.get("name") or path.name),
        "version": str(raw.get("version") or ""),
        "description": str(raw.get("description") or ""),
        "path": str(path),
        "manifest_path": str(manifest_path or ""),
        "tools": [str(item) for item in raw.get("tools", [])],
        "prompt_fragments": [str(item) for item in raw.get("prompt_fragments", [])],
    }


def _matches(plugin: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            str(plugin.get("name") or ""),
            str(plugin.get("description") or ""),
            " ".join(plugin.get("tools") or []),
            " ".join(plugin.get("prompt_fragments") or []),
        ]
    ).lower()
    return query in haystack


def _plugin_payload(plugin: dict[str, Any], *, include_prompt: bool) -> dict[str, Any]:
    payload = dict(plugin)
    if include_prompt:
        payload["prompts"] = _prompt_contents(Path(str(plugin["path"])), plugin.get("prompt_fragments") or [])
    return payload


def _prompt_contents(plugin_dir: Path, fragments: list[str]) -> list[dict[str, str]]:
    prompts: list[dict[str, str]] = []
    plugin_root = plugin_dir.resolve()
    for relative_path in fragments:
        path = (plugin_dir / relative_path).resolve()
        if not _is_relative_to(path, plugin_root):
            prompts.append({"path": str(relative_path), "error": "prompt path escapes plugin root"})
            continue
        try:
            prompts.append({"path": str(relative_path), "content": path.read_text(encoding="utf-8").strip()})
        except OSError as exc:
            prompts.append({"path": str(relative_path), "error": str(exc)})
    return prompts


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_file_stem(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/").split("/")[-1]
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in text)
    return safe.strip(".-")
