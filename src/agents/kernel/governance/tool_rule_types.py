from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedToolRule:
    raw: str
    tool_name: str
    rule_content: str | None = None


@dataclass(frozen=True)
class ShellCommandParts:
    subcommands: tuple[str, ...]
    parse_error: bool = False
    too_complex: bool = False
