from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.interfaces.bridge.payloads import prompt_payload
from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    safe_file_stem,
    set_session_prompt,
    split_once,
    split_once_preserve,
    tool_context,
)
from agents.interfaces.bridge.slash_commands.tool_execution import execute_slash_tool
from agents.kernel.capabilities.tools.builtin.prompts import prompt_delete, prompt_render, prompt_save
from agents.kernel.session_state import save_session_state


async def handle_prompt_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action:
        write({"type": "prompt", "prompt": prompt_payload(state)})
        return
    if action == "show":
        prompt = str(getattr(state.session, "system_prompt", "") or "")
        write({"type": "prompt", "prompt": [["system_prompt", prompt or "empty"]]})
        return
    if action == "set":
        await _handle_prompt_set(state, rest, write=write)
        return
    if action in {"reset", "clear"}:
        await _handle_prompt_reset(state, write=write)
        return
    if action in {"templates", "list"}:
        write({"type": "prompt", "prompt": _prompt_templates_payload(state)})
        return
    if action == "save":
        await _handle_prompt_save(state, rest, write=write)
        return
    if action == "use":
        await _handle_prompt_use(state, rest, write=write)
        return
    if action == "render":
        _handle_prompt_render(state, rest, write=write)
        return
    if action in {"delete", "remove"}:
        await _handle_prompt_delete(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown prompt command: %s" % action})


async def _handle_prompt_set(state: Any, text: str, *, write: BridgeWriter) -> None:
    set_session_prompt(state.session, text)
    await _persist_prompt_override(state, overridden=True)
    if hasattr(state.session, "context_trace"):
        state.session.context_trace = []
    save_session_snapshot(state)
    write({"type": "notice", "message": "session prompt updated"})
    write({"type": "prompt", "prompt": prompt_payload(state)})


async def _handle_prompt_reset(state: Any, *, write: BridgeWriter) -> None:
    set_session_prompt(state.session, _default_system_prompt(state))
    await _persist_prompt_override(state, overridden=False)
    if hasattr(state.session, "context_trace"):
        state.session.context_trace = []
    save_session_snapshot(state)
    write({"type": "notice", "message": "session prompt reset"})
    write({"type": "prompt", "prompt": prompt_payload(state)})


async def _handle_prompt_save(state: Any, rest: str, *, write: BridgeWriter) -> None:
    name, content = split_once_preserve(rest)
    safe_name = safe_file_stem(name)
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt save <name> [text]"})
        return
    text = content.strip() or str(getattr(state.session, "system_prompt", "") or "").strip()
    if not text:
        write({"type": "error", "message": "prompt is empty"})
        return
    context = tool_context(state)
    payload = await execute_slash_tool(
        state,
        tool_name="prompt.save",
        arguments={"name": safe_name, "content": text, "overwrite": True},
        write=write,
        error_label="prompt save",
        fallback=(lambda: prompt_save(context, name=safe_name, content=text, overwrite=True))
        if context is not None
        else (lambda: _prompt_save_local(state, safe_name, text)),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "prompt saved: %s" % safe_name})
    write({"type": "prompt", "prompt": _prompt_templates_payload(state)})


async def _handle_prompt_use(state: Any, rest: str, *, write: BridgeWriter) -> None:
    safe_name = safe_file_stem(rest.strip())
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt use <name>"})
        return
    path = _prompt_template_root(state) / ("%s.md" % safe_name)
    if not path.exists():
        write({"type": "error", "message": "prompt template not found: %s" % safe_name})
        return
    set_session_prompt(state.session, path.read_text(encoding="utf-8"))
    await _persist_prompt_override(state, overridden=True)
    if hasattr(state.session, "context_trace"):
        state.session.context_trace = []
    save_session_snapshot(state)
    write({"type": "notice", "message": "prompt loaded: %s" % safe_name})
    write({"type": "prompt", "prompt": prompt_payload(state)})


def _handle_prompt_render(state: Any, rest: str, *, write: BridgeWriter) -> None:
    name, arguments = split_once_preserve(rest)
    if not name:
        write({"type": "error", "message": "usage: /prompt render <name> [arguments]"})
        return
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        payload = prompt_render(context, name=name, raw_arguments=arguments)
    except Exception as exc:  # noqa: BLE001 - prompt render errors are command output.
        write({"type": "error", "message": "prompt render failed: %s" % exc})
        return
    write({"type": "prompt", "prompt": [["template", payload["name"]], ["prompt", payload["prompt"]]]})


async def _handle_prompt_delete(state: Any, rest: str, *, write: BridgeWriter) -> None:
    safe_name = safe_file_stem(rest.strip())
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt delete <name>"})
        return
    context = tool_context(state)
    payload = await execute_slash_tool(
        state,
        tool_name="prompt.delete",
        arguments={"name": safe_name},
        write=write,
        error_label="prompt delete",
        fallback=(lambda: prompt_delete(context, name=safe_name))
        if context is not None
        else (lambda: _prompt_delete_local(state, safe_name)),
    )
    if payload is None:
        return
    if not payload.get("deleted", True):
        write({"type": "error", "message": "prompt template not found: %s" % safe_name})
        return
    write({"type": "notice", "message": "prompt deleted: %s" % safe_name})
    write({"type": "prompt", "prompt": _prompt_templates_payload(state)})


def _prompt_templates_payload(state: Any) -> list[list[str]]:
    root = _prompt_template_root(state)
    rows: list[list[str]] = []
    for path in sorted(root.glob("*.md")) if root.exists() else []:
        text = path.read_text(encoding="utf-8").strip().replace("\n", " ")
        rows.append([path.stem, text[:120] if text else "empty"])
    return rows or [["templates", "none"]]


async def _persist_prompt_override(state: Any, *, overridden: bool) -> None:
    context = tool_context(state)
    if context is None:
        return
    context.system_prompt_overridden = bool(overridden)
    context.system_prompt_override = str(getattr(state.session, "system_prompt", "") or "") if overridden else ""
    await save_session_state(context)


def _default_system_prompt(state: Any) -> str:
    agent = getattr(getattr(state, "settings", None), "agent", None)
    return str(getattr(agent, "SYSTEM_PROMPT", "") or "")


def _prompt_template_root(state: Any) -> Path:
    base = Path(getattr(state, "active_workspace", "") or getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".") or ".")
    return base.expanduser() / ".agents" / "prompts"


def _prompt_save_local(state: Any, name: str, content: str) -> dict[str, Any]:
    root = _prompt_template_root(state)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("%s.md" % name)
    text = str(content or "")
    path.write_text(text, encoding="utf-8")
    return {"name": name, "path": str(path), "bytes": len(text.encode("utf-8"))}


def _prompt_delete_local(state: Any, name: str) -> dict[str, Any]:
    path = _prompt_template_root(state) / ("%s.md" % name)
    if not path.exists():
        return {"name": name, "path": str(path), "deleted": False}
    path.unlink()
    return {"name": name, "path": str(path), "deleted": True}
