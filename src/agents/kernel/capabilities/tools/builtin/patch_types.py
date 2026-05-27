from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlannedFile:
    path: str
    before: str
    after: str
    action: str
    encoding: str = "utf-8"
    edit_count: int = 0
    symlink_target: str = ""


@dataclass
class PlannedEdit:
    path: str
    old_text: str
    new_text: str
    replace_all: bool
    occurrences: int
    original_file: str
