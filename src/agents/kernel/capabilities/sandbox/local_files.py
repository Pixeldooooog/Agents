from __future__ import annotations

import stat
from pathlib import Path

from .text import python_text_codec, write_encoding_name


def ensure_regular_file(path: Path, display_path: str, *, operation: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_file():
        return
    if path.is_dir():
        raise IsADirectoryError("refusing to %s directory: %s" % (operation, display_path))
    special_kind = special_file_kind(path) or "non-regular file"
    raise ValueError("refusing to %s special file (%s): %s" % (operation, special_kind, display_path))


def special_file_kind(path: Path) -> str | None:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character device"
    if stat.S_ISBLK(mode):
        return "block device"
    return None


def write_encoding(encoding: str) -> str:
    return write_encoding_name(encoding)


def optional_positive_int(value: int | None) -> int | None:
    if value is None or value == "":
        return None
    return max(1, int(value))


def read_text_line_range(path: Path, *, encoding: str, line_offset: int, line_limit: int | None) -> str:
    selected: list[str] = []
    with path.open("r", encoding=python_text_codec(encoding), errors="replace", newline="") as handle:
        for index, line in enumerate(handle):
            if index < line_offset:
                continue
            if line_limit is not None and len(selected) >= line_limit:
                break
            selected.append(line)
    return "".join(selected)


def count_text_lines(path: Path, encoding: str) -> int:
    count = 0
    with path.open("r", encoding=python_text_codec(encoding), errors="replace", newline="") as handle:
        for count, _ in enumerate(handle, start=1):
            pass
    return count


def line_count(content: str) -> int:
    if not content:
        return 0
    return len(content.splitlines())
