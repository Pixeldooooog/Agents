from __future__ import annotations

from pathlib import PurePosixPath


def is_team_memory_path(path: str) -> bool:
    parts = PurePosixPath(str(path or "").replace("\\", "/")).parts
    for index, part in enumerate(parts):
        if part != ".agents":
            continue
        tail = parts[index + 1 :]
        if len(tail) >= 3 and tail[0] in {"memory", "memories"} and tail[1] == "team":
            return True
        if len(tail) >= 5 and tail[0] == "projects" and tail[2] == "memory" and tail[3] == "team":
            return True
    return False
