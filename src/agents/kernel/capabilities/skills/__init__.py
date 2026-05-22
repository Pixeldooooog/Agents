# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：skills.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    prompt_fragments: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    path_patterns: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillDependencyError(ValueError):
    """Raised when skill dependency resolution fails."""


class SkillLoader:
    def __init__(self, root: Path):
        self.root = Path(root)

    def load(self, name: str, context: Optional[Dict[str, Any]] = None) -> SkillManifest:
        manifest_path = self._manifest_path(name)
        return self.load_manifest(manifest_path, context=context)

    def load_manifest(self, manifest_path: Path, context: Optional[Dict[str, Any]] = None) -> SkillManifest:
        manifest_path = Path(manifest_path)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        fragment_root = self.root if manifest_path.parent == self.root / "skills" else manifest_path.parent
        render_context = context or {}
        fragments = []
        for relative_path in raw.get("prompt_fragments", []):
            text = (fragment_root / relative_path).read_text(encoding="utf-8")
            fragments.append(text.format(**render_context).strip())
        metadata = dict(raw.get("metadata", {}))
        path_patterns = coerce_path_patterns(raw.get("paths", metadata.get("paths")))
        if path_patterns:
            metadata.setdefault("paths", list(path_patterns))
        return SkillManifest(
            name=raw["name"],
            version=raw.get("version", "0.1.0"),
            description=raw.get("description", ""),
            dependencies=list(raw.get("dependencies", raw.get("requires", []))),
            prompt_fragments=fragments,
            tools=list(raw.get("tools", [])),
            path_patterns=path_patterns,
            metadata=metadata,
        )

    def _manifest_path(self, name: str) -> Path:
        skills_dir = self.root / "skills"
        flat = skills_dir / ("%s.json" % name)
        if flat.exists():
            return flat
        packaged = skills_dir / name / "skill.json"
        if packaged.exists():
            return packaged
        return flat


class SkillRegistry:
    def __init__(self, skills: Iterable[SkillManifest]):
        self.skills = list(skills)

    @classmethod
    def load(cls, loader: SkillLoader, names: Iterable[str], context: Optional[Dict[str, Any]] = None) -> "SkillRegistry":
        ordered: List[SkillManifest] = []
        resolved = set()
        visiting: List[str] = []

        def visit(name: str) -> None:
            if name in resolved:
                return
            if name in visiting:
                raise SkillDependencyError("skill dependency cycle: %s" % " -> ".join(visiting + [name]))
            visiting.append(name)
            skill = loader.load(name, context=context)
            for dependency in skill.dependencies:
                visit(dependency)
            visiting.pop()
            resolved.add(skill.name)
            ordered.append(skill)

        for name in names:
            visit(name)
        return cls(ordered)

    def names(self) -> List[str]:
        return [skill.name for skill in self.skills]

    def add_or_replace(self, skill: SkillManifest) -> None:
        self.skills = [item for item in self.skills if item.name != skill.name] + [skill]

    def prompt_text(self) -> str:
        return "\n\n".join(fragment for skill in self.skills for fragment in skill.prompt_fragments if fragment)

    def tool_names(self) -> List[str]:
        names: List[str] = []
        seen = set()
        for skill in self.skills:
            for tool_name in skill.tools:
                if tool_name not in seen:
                    seen.add(tool_name)
                    names.append(tool_name)
        return names


def coerce_path_patterns(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values: list[Any] = []
        for line in raw.splitlines():
            values.extend(line.split(","))
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [raw]

    patterns: list[str] = []
    for value in values:
        pattern = str(value or "").strip().replace("\\", "/")
        if not pattern:
            continue
        if pattern.startswith("./"):
            pattern = pattern[2:]
        if pattern.endswith("/**"):
            pattern = pattern[:-3]
        if pattern:
            patterns.append(pattern)
    if not patterns or all(pattern == "**" for pattern in patterns):
        return []
    return patterns
