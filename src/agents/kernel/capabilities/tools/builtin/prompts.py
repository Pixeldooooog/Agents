from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


PROMPT_TEMPLATES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional text filter over template name and preview."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

PROMPT_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt template name without .md."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
    "required": ["name"],
}

PROMPT_RENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt template name without .md."},
        "arguments": {"type": "object", "description": "Named values for {{name}} or {name} placeholders."},
        "raw_arguments": {"type": "string", "description": "Raw argument text for {{arguments}} or {arguments} placeholders."},
    },
    "required": ["name"],
}

PROMPT_SAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt template name without .md."},
        "content": {"type": "string"},
        "overwrite": {"type": "boolean", "description": "Allow replacing an existing prompt template."},
    },
    "required": ["name", "content"],
}

PROMPT_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt template name without .md."},
    },
    "required": ["name"],
}


def prompt_templates(
    context: ToolRuntimeContext,
    query: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    templates = _list_templates(context)
    needle = str(query or "").strip().lower()
    if needle:
        templates = [template for template in templates if needle in _template_haystack(template)]
    limit = max(1, min(int(max_results or 50), 100))
    return {
        "templates": templates[:limit],
        "count": min(len(templates), limit),
        "total": len(templates),
    }


def prompt_read(context: ToolRuntimeContext, name: str, max_bytes: int = 20000) -> dict[str, Any]:
    template_name = _safe_template_name(name)
    result = context.sandbox_client.read_text(_template_path(template_name), max_bytes=max(1, min(int(max_bytes or 20000), 200000)))
    return {
        "name": template_name,
        "path": result.path,
        "content": result.content,
        "bytes": result.bytes,
        "truncated": result.truncated,
    }


def prompt_render(
    context: ToolRuntimeContext,
    name: str,
    arguments: dict[str, Any] | None = None,
    raw_arguments: str = "",
) -> dict[str, Any]:
    read = prompt_read(context, name=name, max_bytes=200000)
    rendered = _render_template(read["content"], arguments=arguments or {}, raw_arguments=str(raw_arguments or ""))
    return {
        "name": read["name"],
        "path": read["path"],
        "arguments": {str(key): str(value) for key, value in dict(arguments or {}).items()},
        "raw_arguments": str(raw_arguments or ""),
        "prompt": rendered,
    }


def prompt_save(context: ToolRuntimeContext, name: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    template_name = _safe_template_name(name)
    path = _template_path(template_name)
    if not overwrite and _template_exists(context, template_name):
        raise FileExistsError("prompt template already exists: %s" % template_name)
    result = context.sandbox_client.write_text(path, str(content or ""))
    return {"name": template_name, "path": result.path, "bytes": result.bytes}


def prompt_delete(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    template_name = _safe_template_name(name)
    path = _template_path(template_name)
    result = context.sandbox_client.delete_path(path)
    return {"name": template_name, "path": path, "deleted": bool(result.get("deleted", True)), "result": result}


def _list_templates(context: ToolRuntimeContext) -> list[dict[str, Any]]:
    try:
        listing = context.sandbox_client.list_dir(".agents/prompts")
    except Exception:  # noqa: BLE001 - missing prompt directory simply means no templates.
        return []
    templates: list[dict[str, Any]] = []
    for entry in listing.entries:
        if entry.type != "file" or not entry.name.endswith(".md"):
            continue
        name = entry.name[:-3]
        try:
            read = context.sandbox_client.read_text(entry.path, max_bytes=240)
            preview = " ".join(read.content.split())
        except Exception:  # noqa: BLE001 - a broken template should still be visible.
            preview = ""
        templates.append({"name": name, "path": entry.path, "preview": preview[:160]})
    return sorted(templates, key=lambda item: item["name"])


def _template_exists(context: ToolRuntimeContext, name: str) -> bool:
    try:
        context.sandbox_client.read_text(_template_path(name), max_bytes=1)
        return True
    except Exception:  # noqa: BLE001 - any read failure here means overwrite protection can allow creation.
        return False


def _template_haystack(template: dict[str, Any]) -> str:
    return ("%s %s" % (template.get("name", ""), template.get("preview", ""))).lower()


def _render_template(content: str, arguments: dict[str, Any], raw_arguments: str) -> str:
    rendered = str(content or "")
    replacements = {"arguments": raw_arguments}
    replacements.update({str(key): str(value) for key, value in dict(arguments or {}).items()})
    for key, value in replacements.items():
        rendered = rendered.replace("{{%s}}" % key, value).replace("{%s}" % key, value)
    return rendered


def _template_path(name: str) -> str:
    return ".agents/prompts/%s.md" % name


def _safe_template_name(value: Any) -> str:
    text = str(value or "").strip()
    name = "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")
    if not name:
        raise ValueError("name is required")
    if "/" in text or "\\" in text or name in {".", ".."}:
        raise ValueError("prompt template name must not contain path separators")
    return name
