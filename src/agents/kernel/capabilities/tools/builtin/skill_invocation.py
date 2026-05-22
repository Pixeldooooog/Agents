from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.kernel.capabilities.skills import SkillLoader, SkillManifest
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec


SKILL_INVOKE_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "string", "description": "Skill name, with or without a leading slash."},
        "args": {"type": "string", "description": "Optional arguments for the skill."},
        "mode": {"type": "string", "enum": ["auto", "inline", "fork"], "description": "Execution mode override."},
    },
    "required": ["skill"],
    "additionalProperties": False,
}


async def skill_invoke(
    context: ToolRuntimeContext,
    *,
    skill: str,
    args: str = "",
    mode: str = "auto",
) -> dict[str, Any]:
    manifest = _load_skill(context, skill, args=args)
    prompt = _render_skill_prompt(manifest, args)
    execution_mode = _execution_mode(manifest, mode)
    if execution_mode == "fork":
        return await _invoke_forked(context, manifest, prompt, args)
    return {
        "success": True,
        "commandName": manifest.name,
        "allowedTools": list(manifest.tools),
        "model": str(manifest.metadata.get("model") or ""),
        "status": "inline",
        "args": str(args or ""),
        "prompt": prompt,
    }


def format_skill_invoke_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    command_name = str(result.get("commandName") or result.get("skill") or "")
    if result.get("status") == "forked":
        return "Skill %s completed in a forked agent:\n%s" % (command_name, str(result.get("result") or ""))
    prompt = str(result.get("prompt") or "")
    if prompt:
        return "Skill %s invoked. Continue using these instructions:\n%s" % (command_name, prompt)
    return "Skill %s invoked." % command_name


def _load_skill(context: ToolRuntimeContext, name: str, *, args: str = "") -> SkillManifest:
    root = _settings_root(context)
    normalized = _skill_name(name)
    try:
        return SkillLoader(root).load(normalized, context={"arguments": str(args or "")})
    except FileNotFoundError:
        pass
    for skills_dir in sorted(getattr(context, "dynamic_skill_dirs", set()) or set()):
        try:
            return SkillLoader(Path(skills_dir).parent).load(normalized, context={"arguments": str(args or "")})
        except FileNotFoundError:
            continue
    raise FileNotFoundError("unknown skill: %s" % normalized)


def _render_skill_prompt(skill: SkillManifest, args: str) -> str:
    fragments = [fragment.strip() for fragment in skill.prompt_fragments if str(fragment or "").strip()]
    prompt = "\n\n".join(fragments).strip()
    if not prompt:
        prompt = skill.description.strip()
    if str(args or "").strip():
        prompt = "%s\n\nArguments:\n%s" % (prompt, str(args).strip()) if prompt else str(args).strip()
    return prompt


def _execution_mode(skill: SkillManifest, mode: str) -> str:
    value = str(mode or "auto").strip().lower()
    if value not in {"auto", "inline", "fork"}:
        raise ValueError("unknown skill execution mode: %s" % mode)
    if value != "auto":
        return value
    metadata = dict(skill.metadata or {})
    configured = str(metadata.get("context") or metadata.get("execution") or metadata.get("execution_mode") or "inline").strip().lower()
    return "fork" if configured == "fork" else "inline"


async def _invoke_forked(
    context: ToolRuntimeContext,
    skill: SkillManifest,
    prompt: str,
    args: str,
) -> dict[str, Any]:
    if context.agent_session_factory is None:
        raise RuntimeError("agent session factory is not available")
    if int(context.subagent_depth or 0) >= int(context.max_subagent_depth or 1):
        raise RuntimeError("subagent depth limit reached")
    child_spec = _child_spec(context, skill)
    child = await context.agent_session_factory(child_spec, task_id="")
    run_id = "skill_%s" % uuid4().hex
    try:
        result = await child.send(prompt, run_id=run_id)
    finally:
        close = getattr(child, "aclose", None)
        if close is not None:
            await close()
    return {
        "success": True,
        "commandName": skill.name,
        "status": "forked",
        "agentId": child_spec.agent_id,
        "run_id": run_id,
        "args": str(args or ""),
        "result": str(getattr(result, "content", "") or ""),
    }


def _child_spec(context: ToolRuntimeContext, skill: SkillManifest) -> AgentSpec:
    base = _agent_spec(context)
    child_agent_id = "skill_%s_%s" % (_safe_token(skill.name), uuid4().hex[:8])
    workspace = replace(base.workspace, agent_id=child_agent_id)
    metadata = dict(base.metadata)
    metadata.update(
        {
            "parent_agent_id": base.agent_id or base.workspace.agent_id,
            "skill": skill.name,
            "description": "Execute skill: %s" % skill.name,
        }
    )
    tools = list(skill.tools) if skill.tools else base.enabled_tools
    return replace(
        base,
        agent_id=child_agent_id,
        workspace=workspace,
        enabled_tools=list(tools) if tools is not None else None,
        metadata=metadata,
    )


def _agent_spec(context: ToolRuntimeContext) -> AgentSpec:
    spec = getattr(context, "agent_spec", None)
    if isinstance(spec, AgentSpec):
        return spec
    workspace = context.workspace
    return AgentSpec.from_overrides(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        workspace_path=str(workspace.path),
        enabled_tools=list(getattr(context, "enabled_tools", []) or []),
    )


def _settings_root(context: ToolRuntimeContext):
    root = getattr(getattr(context.settings, "server", None), "ROOT_PATH", "") if context.settings is not None else ""
    return context.workspace.path if not root else root


def _skill_name(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("/"):
        text = text[1:]
    if not text:
        raise ValueError("skill is required")
    return text


def _safe_token(value: str) -> str:
    token = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")
    return token or "skill"
