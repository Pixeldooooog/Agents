from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


COMMAND_DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

COMMAND_RENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt-backed command name, with or without leading slash."},
        "arguments": {"type": "string", "description": "Raw command argument text to inject as {arguments}."},
    },
    "required": ["name"],
}

COMMAND_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt-backed command name, with or without leading slash."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
    "required": ["name"],
}

COMMAND_SAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Command name, with or without leading slash."},
        "content": {"type": "string", "description": "Prompt body. {arguments} is replaced by raw command arguments."},
        "description": {"type": "string"},
        "argument_hint": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "overwrite": {"type": "boolean"},
    },
    "required": ["name", "content"],
}

COMMAND_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt-backed command name, with or without leading slash."},
    },
    "required": ["name"],
}


def command_discover(context: ToolRuntimeContext, query: str = "", max_results: int = 50) -> dict[str, Any]:
    commands = _discover_commands(context)
    needle = str(query or "").strip().lower()
    if needle:
        commands = [command for command in commands if needle in _command_haystack(command)]
    limit = max(1, min(int(max_results or 50), 100))
    return {"commands": commands[:limit], "count": min(len(commands), limit), "total": len(commands)}


def command_render(context: ToolRuntimeContext, name: str, arguments: str = "") -> dict[str, Any]:
    command_name = _command_name(name)
    matches = [command for command in _discover_commands(context) if command["name"] == command_name or command_name in command["aliases"]]
    if not matches:
        raise FileNotFoundError("command not found: %s" % command_name)
    command = matches[0]
    body = Path(command["path"]).read_text(encoding="utf-8")
    _, content = _frontmatter(body)
    rendered = _render_arguments(content.strip(), str(arguments or ""))
    return {"command": command, "arguments": str(arguments or ""), "prompt": rendered}


def command_read(context: ToolRuntimeContext, name: str, max_bytes: int = 20000) -> dict[str, Any]:
    command = _find_command(context, name)
    result = context.sandbox_client.read_text(_relative_to_workspace(context, Path(command["path"])), max_bytes=max(1, min(int(max_bytes or 20000), 200000)))
    metadata, content = _frontmatter(result.content)
    return {
        "command": command,
        "metadata": metadata,
        "content": content,
        "path": result.path,
        "bytes": result.bytes,
        "truncated": result.truncated,
    }


def command_save(
    context: ToolRuntimeContext,
    name: str,
    content: str,
    description: str = "",
    argument_hint: str = "",
    aliases: list[str] | None = None,
    category: str = "custom",
    overwrite: bool = False,
) -> dict[str, Any]:
    command_name = _command_name(name)
    path = _command_path(command_name)
    if not overwrite and _command_exists(context, path):
        raise FileExistsError("command already exists: %s" % command_name)
    body = _command_file_content(
        command_name,
        content=str(content or ""),
        description=description,
        argument_hint=argument_hint,
        aliases=aliases,
        category=category,
    )
    result = context.sandbox_client.write_text(path, body)
    return {"name": command_name, "path": result.path, "bytes": result.bytes}


def command_delete(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    try:
        command = _find_command(context, name)
        path = _relative_to_workspace(context, Path(command["path"]))
    except FileNotFoundError:
        path = _command_path(_command_name(name))
    result = context.sandbox_client.delete_path(path)
    return {"name": _command_name(name), "path": path, "deleted": bool(result.get("deleted", True)), "result": result}


def _discover_commands(context: ToolRuntimeContext) -> list[dict[str, Any]]:
    root = Path(context.workspace.path)
    commands: list[dict[str, Any]] = []
    for command_dir in [root / ".agents" / "commands", root / "commands"]:
        if not command_dir.exists():
            continue
        for path in sorted(command_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta, body = _frontmatter(raw)
            name = _command_name(str(meta.get("name") or path.stem))
            aliases = [_command_name(item) for item in _csv(meta.get("aliases", ""))]
            commands.append(
                {
                    "name": name,
                    "description": str(meta.get("description") or _description_from_body(body) or ""),
                    "argumentHint": str(meta.get("argument_hint") or meta.get("argumentHint") or ""),
                    "aliases": aliases,
                    "source": "workspace",
                    "category": str(meta.get("category") or "custom"),
                    "path": str(path),
                }
            )
    return sorted(commands, key=lambda item: item["name"])


def _find_command(context: ToolRuntimeContext, name: str) -> dict[str, Any]:
    command_name = _command_name(name)
    matches = [command for command in _discover_commands(context) if command["name"] == command_name or command_name in command["aliases"]]
    if not matches:
        raise FileNotFoundError("command not found: %s" % command_name)
    return matches[0]


def _frontmatter(raw: str) -> tuple[dict[str, str], str]:
    text = str(raw or "")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    block = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


def _description_from_body(body: str) -> str:
    for line in str(body or "").splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:160]
    return ""


def _render_arguments(content: str, arguments: str) -> str:
    return content.replace("{{arguments}}", arguments).replace("{arguments}", arguments)


def _command_file_content(
    command_name: str,
    *,
    content: str,
    description: str = "",
    argument_hint: str = "",
    aliases: list[str] | None = None,
    category: str = "custom",
) -> str:
    metadata = {
        "name": command_name.lstrip("/"),
        "description": str(description or ""),
        "argument_hint": str(argument_hint or ""),
        "aliases": ", ".join(alias.lstrip("/") for alias in aliases or [] if str(alias or "").strip()),
        "category": str(category or "custom"),
    }
    lines = ["---"]
    for key, value in metadata.items():
        if value:
            lines.append("%s: %s" % (key, value))
    lines.extend(["---", str(content or "").strip(), ""])
    return "\n".join(lines)


def _command_name(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("/"):
        text = text[1:]
    name = "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")
    if not name:
        raise ValueError("name is required")
    return "/%s" % name


def _command_path(command_name: str) -> str:
    return ".agents/commands/%s.md" % command_name.lstrip("/")


def _command_exists(context: ToolRuntimeContext, path: str) -> bool:
    try:
        context.sandbox_client.read_text(path, max_bytes=1)
        return True
    except Exception:
        return False


def _relative_to_workspace(context: ToolRuntimeContext, path: Path) -> str:
    root = Path(context.workspace.path).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise PermissionError("command path escapes workspace: %s" % path) from exc


def _csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _command_haystack(command: dict[str, Any]) -> str:
    return " ".join(
        [
            str(command.get("name") or ""),
            str(command.get("description") or ""),
            str(command.get("argumentHint") or ""),
            " ".join(command.get("aliases") or []),
            str(command.get("category") or ""),
        ]
    ).lower()
