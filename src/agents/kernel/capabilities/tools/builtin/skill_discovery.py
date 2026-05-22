from __future__ import annotations

from pathlib import Path

from agents.kernel.capabilities.skills import SkillLoader, SkillRegistry
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def discover_dynamic_skills_for_paths(context: ToolRuntimeContext, paths: list[str]) -> list[str]:
    """Discover nested .claude/skills directories touched by file tools."""
    discovered: list[str] = []
    root = Path(context.workspace.path).resolve()
    for raw_path in paths:
        for skills_dir in _candidate_skill_dirs(context, root, raw_path):
            skills_dir_key = str(skills_dir)
            checked = getattr(context, "dynamic_skill_dirs_checked", set())
            if skills_dir_key in checked:
                continue
            checked.add(skills_dir_key)
            context.dynamic_skill_dirs_checked = checked
            if not skills_dir.is_dir():
                continue
            context.dynamic_skill_dirs.add(skills_dir_key)
            context.dynamic_skill_dir_triggers.add(skills_dir_key)
            _load_dynamic_skill_dir(context, skills_dir)
            discovered.append(skills_dir_key)
    return discovered


def _candidate_skill_dirs(context: ToolRuntimeContext, root: Path, raw_path: str):
    try:
        resolved = context.sandbox.resolve_workspace_path(raw_path)
    except Exception:
        return
    current = resolved if resolved.is_dir() else resolved.parent
    while _is_strictly_inside(current, root):
        yield current / ".claude" / "skills"
        parent = current.parent
        if parent == current:
            break
        current = parent


def _is_strictly_inside(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts)


def _load_dynamic_skill_dir(context: ToolRuntimeContext, skills_dir: Path) -> None:
    registry = getattr(context, "skill_registry", None)
    if registry is None:
        registry = SkillRegistry([])
        context.skill_registry = registry
    loader = SkillLoader(skills_dir.parent)
    for manifest_path in _skill_manifest_paths(skills_dir):
        try:
            registry.add_or_replace(loader.load_manifest(manifest_path, context={"arguments": ""}))
        except (FileNotFoundError, KeyError, ValueError):
            continue


def _skill_manifest_paths(skills_dir: Path) -> list[Path]:
    if not skills_dir.exists():
        return []
    return sorted([*skills_dir.glob("*.json"), *skills_dir.glob("*/skill.json")])
