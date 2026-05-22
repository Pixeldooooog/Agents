from __future__ import annotations

import fnmatch
import json
import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

from agents.kernel.capabilities.skills import (
    SkillLoader,
    SkillRegistry,
    coerce_path_patterns,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def discover_dynamic_skills_for_paths(context: ToolRuntimeContext, paths: list[str]) -> list[str]:
    """Discover nested .claude/skills directories touched by file tools."""
    activate_conditional_skills_for_paths(context, paths)
    discovered: list[str] = []
    root = Path(context.workspace.path).resolve()
    for raw_path in paths:
        for skills_dir, containing_dir in _candidate_skill_dirs(
            context,
            root,
            raw_path,
        ):
            skills_dir_key = str(skills_dir)
            checked = getattr(context, "dynamic_skill_dirs_checked", set())
            if skills_dir_key in checked:
                continue
            checked.add(skills_dir_key)
            context.dynamic_skill_dirs_checked = checked
            if not skills_dir.is_dir():
                continue
            if _is_path_gitignored(root, containing_dir):
                continue
            context.dynamic_skill_dirs.add(skills_dir_key)
            context.dynamic_skill_dir_triggers.add(skills_dir_key)
            _load_dynamic_skill_dir(context, skills_dir)
            discovered.append(skills_dir_key)
    return discovered


def activate_conditional_skills_for_paths(context: ToolRuntimeContext, paths: list[str]) -> list[str]:
    """Activate root skills whose path patterns match touched workspace files."""
    root = Path(context.workspace.path).resolve()
    relative_paths = _workspace_relative_paths(context, root, paths)
    if not relative_paths:
        return []

    activated: list[str] = []
    registry = getattr(context, "skill_registry", None)
    active_names = set(registry.names()) if registry is not None else set()
    loader = SkillLoader(_settings_root(context))
    for manifest_path in _skill_manifest_paths(loader.root / "skills"):
        candidate = _conditional_skill_candidate(manifest_path)
        if candidate is None:
            continue
        name, patterns = candidate
        if name in active_names:
            continue
        matched_path = _first_matching_path(relative_paths, patterns)
        if matched_path is None:
            continue
        try:
            skill = loader.load_manifest(manifest_path, context={"arguments": ""})
        except (FileNotFoundError, KeyError, ValueError):
            continue
        registry = _ensure_skill_registry(context)
        registry.add_or_replace(skill)
        active_names.add(skill.name)
        activated.append(skill.name)
        context.conditional_skill_names_activated.add(skill.name)
        context.conditional_skill_triggers[skill.name] = matched_path
    return activated


def _candidate_skill_dirs(context: ToolRuntimeContext, root: Path, raw_path: str):
    try:
        resolved = context.sandbox.resolve_workspace_path(raw_path)
    except Exception:
        return
    current = resolved if resolved.is_dir() else resolved.parent
    while _is_strictly_inside(current, root):
        yield current / ".claude" / "skills", current
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


def _workspace_relative_paths(context: ToolRuntimeContext, root: Path, paths: list[str]) -> list[str]:
    relative_paths: list[str] = []
    seen = set()
    for raw_path in paths:
        try:
            resolved = context.sandbox.resolve_workspace_path(raw_path)
            relative = resolved.resolve().relative_to(root)
        except Exception:
            continue
        value = relative.as_posix()
        if value and value not in seen:
            seen.add(value)
            relative_paths.append(value)
    return relative_paths


def _first_matching_path(paths: list[str], patterns: list[str]) -> str | None:
    for path in paths:
        if any(_path_matches_pattern(path, pattern) for pattern in patterns):
            return path
    return None


def _conditional_skill_candidate(manifest_path: Path) -> tuple[str, list[str]] | None:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    patterns = coerce_path_patterns(raw.get("paths", metadata.get("paths")))
    if not patterns:
        return None
    default_name = (
        manifest_path.parent.name
        if manifest_path.name == "skill.json"
        else manifest_path.stem
    )
    return str(raw.get("name") or default_name), patterns


@lru_cache(maxsize=2048)
def _path_matches_pattern(path: str, pattern: str) -> bool:
    normalized_path = path.strip("/").replace("\\", "/")
    normalized_pattern = pattern.strip().strip("/").replace("\\", "/")
    if not normalized_path or not normalized_pattern:
        return False
    if normalized_pattern == "**":
        return False
    if _is_plain_path_pattern(normalized_pattern):
        return normalized_path == normalized_pattern or normalized_path.startswith(
            f"{normalized_pattern}/"
        )
    if PurePosixPath(normalized_path).match(normalized_pattern):
        return True
    if "/" not in normalized_pattern and fnmatch.fnmatchcase(
        PurePosixPath(normalized_path).name,
        normalized_pattern,
    ):
        return True
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def _is_plain_path_pattern(pattern: str) -> bool:
    return not any(char in pattern for char in "*?[")


def _is_path_gitignored(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    if not relative.parts:
        return False

    check_path = relative.as_posix()
    if path.is_dir():
        check_path = f"{check_path}/"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", "--", check_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _load_dynamic_skill_dir(context: ToolRuntimeContext, skills_dir: Path) -> None:
    registry = _ensure_skill_registry(context)
    loader = SkillLoader(skills_dir.parent)
    for manifest_path in _skill_manifest_paths(skills_dir):
        try:
            registry.add_or_replace(
                loader.load_manifest(manifest_path, context={"arguments": ""})
            )
        except (FileNotFoundError, KeyError, ValueError):
            continue


def _ensure_skill_registry(context: ToolRuntimeContext) -> SkillRegistry:
    registry = getattr(context, "skill_registry", None)
    if registry is None:
        registry = SkillRegistry([])
        context.skill_registry = registry
    return registry


def _settings_root(context: ToolRuntimeContext) -> Path:
    settings = getattr(context, "settings", None)
    root = (
        getattr(getattr(settings, "server", None), "ROOT_PATH", "")
        if settings is not None
        else ""
    )
    return Path(root or context.workspace.root or context.workspace.path).expanduser()


def _skill_manifest_paths(skills_dir: Path) -> list[Path]:
    if not skills_dir.exists():
        return []
    return sorted([*skills_dir.glob("*.json"), *skills_dir.glob("*/skill.json")])
