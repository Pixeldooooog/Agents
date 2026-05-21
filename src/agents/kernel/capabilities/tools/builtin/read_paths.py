from __future__ import annotations

import re
from pathlib import Path

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


THIN_SPACE = "\u202f"
SCREENSHOT_AM_PM_RE = re.compile(r"^(.+)([ \u202f])(AM|PM)(\.png)$")


def existing_alternate_screenshot_path(context: ToolRuntimeContext, path: str) -> str | None:
    alternate = alternate_screenshot_path(path)
    if not alternate:
        return None
    try:
        resolved = context.sandbox.resolve_workspace_path(alternate)
    except (OSError, PermissionError):
        return None
    if not resolved.is_file():
        return None
    return context.sandbox.relative_workspace_path(resolved)


def alternate_screenshot_path(path: str) -> str | None:
    file_path = Path(path)
    match = SCREENSHOT_AM_PM_RE.match(file_path.name)
    if not match:
        return None
    current_space = match.group(2)
    alternate_space = THIN_SPACE if current_space == " " else " "
    alternate_name = "%s%s%s%s" % (match.group(1), alternate_space, match.group(3), match.group(4))
    return str(file_path.with_name(alternate_name))
