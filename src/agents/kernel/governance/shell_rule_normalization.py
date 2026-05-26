from __future__ import annotations

import re
from typing import Literal


ShellEnvMode = Literal["all", "safe"]

_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_SAFE_ENV_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./:-]+)$")
_SAFE_TIMEOUT_VALUE_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_TIMEOUT_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_NICE_LEVEL_RE = re.compile(r"^-?\d+$")
_STDBUF_OPTION_RE = re.compile(r"^-[ioe][LN0-9]+$")
_SAFE_ENV_VARS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "BLOCK_SIZE",
        "BLOCKSIZE",
        "CGO_ENABLED",
        "CHARSET",
        "COLORTERM",
        "FORCE_COLOR",
        "GCC_COLORS",
        "GO111MODULE",
        "GOARCH",
        "GOEXPERIMENT",
        "GOOS",
        "GREP_COLOR",
        "GREP_COLORS",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LC_TIME",
        "LSCOLORS",
        "LS_COLORS",
        "NODE_ENV",
        "NO_COLOR",
        "PYTEST_DEBUG",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "RUST_BACKTRACE",
        "RUST_LOG",
        "TERM",
        "TIME_STYLE",
        "TZ",
    }
)


def normalize_shell_segment(tokens: list[str], *, env_mode: ShellEnvMode = "all") -> str:
    if env_mode == "safe":
        return _normalize_shell_segment_for_allow(tokens)
    return _normalize_shell_segment_for_deny_or_ask(tokens)


def _normalize_shell_segment_for_deny_or_ask(tokens: list[str]) -> str:
    index = 0
    previous_index = -1
    while index != previous_index and index < len(tokens):
        previous_index = index
        while index < len(tokens) and _is_env_assignment(tokens[index]):
            index += 1
        index = _skip_safe_shell_wrapper(tokens, index)
    return " ".join(tokens[index:]).strip()


def _normalize_shell_segment_for_allow(tokens: list[str]) -> str:
    index = 0
    while index < len(tokens) and _is_safe_env_assignment(tokens[index]):
        index += 1

    previous_index = -1
    while index != previous_index and index < len(tokens):
        previous_index = index
        index = _skip_safe_shell_wrapper(tokens, index)
    return " ".join(tokens[index:]).strip()


def _skip_safe_shell_wrapper(tokens: list[str], index: int) -> int:
    if index >= len(tokens):
        return index
    command = str(tokens[index] or "")
    if command == "timeout":
        return _skip_timeout_wrapper(tokens, index)
    if command == "time":
        return _skip_optional_double_dash(tokens, index + 1)
    if command == "nice":
        return _skip_nice_wrapper(tokens, index)
    if command == "stdbuf":
        return _skip_stdbuf_wrapper(tokens, index)
    if command == "nohup":
        return _skip_optional_double_dash(tokens, index + 1)
    return index


def _skip_timeout_wrapper(tokens: list[str], index: int) -> int:
    cursor = index + 1
    while cursor < len(tokens):
        token = str(tokens[cursor] or "")
        if token in {"--foreground", "--preserve-status", "--verbose", "-v"}:
            cursor += 1
            continue
        if token in {"--kill-after", "--signal", "-k", "-s"}:
            if cursor + 1 >= len(tokens) or not _SAFE_TIMEOUT_VALUE_RE.match(str(tokens[cursor + 1] or "")):
                return index
            cursor += 2
            continue
        if token.startswith("--kill-after=") or token.startswith("--signal="):
            value = token.split("=", 1)[1]
            if not _SAFE_TIMEOUT_VALUE_RE.match(value):
                return index
            cursor += 1
            continue
        if (token.startswith("-k") or token.startswith("-s")) and len(token) > 2:
            if not _SAFE_TIMEOUT_VALUE_RE.match(token[2:]):
                return index
            cursor += 1
            continue
        break
    if cursor < len(tokens) and tokens[cursor] == "--":
        cursor += 1
    if cursor < len(tokens) and _TIMEOUT_DURATION_RE.match(str(tokens[cursor] or "")):
        return cursor + 1
    return index


def _skip_nice_wrapper(tokens: list[str], index: int) -> int:
    cursor = index + 1
    if cursor + 1 < len(tokens) and tokens[cursor] == "-n" and _NICE_LEVEL_RE.match(str(tokens[cursor + 1] or "")):
        cursor += 2
    elif cursor < len(tokens) and str(tokens[cursor] or "").startswith("-") and _NICE_LEVEL_RE.match(str(tokens[cursor])[1:]):
        cursor += 1
    if cursor < len(tokens) and tokens[cursor] == "--":
        cursor += 1
    return cursor if cursor > index + 1 else index + 1


def _skip_stdbuf_wrapper(tokens: list[str], index: int) -> int:
    cursor = index + 1
    while cursor < len(tokens) and _STDBUF_OPTION_RE.match(str(tokens[cursor] or "")):
        cursor += 1
    if cursor == index + 1:
        return index
    if cursor < len(tokens) and tokens[cursor] == "--":
        cursor += 1
    return cursor


def _skip_optional_double_dash(tokens: list[str], index: int) -> int:
    return index + 1 if index < len(tokens) and tokens[index] == "--" else index


def _is_env_assignment(token: str) -> bool:
    return bool(_ENV_ASSIGNMENT_RE.match(str(token or "")))


def _is_safe_env_assignment(token: str) -> bool:
    match = _SAFE_ENV_ASSIGNMENT_RE.match(str(token or ""))
    return bool(match and match.group(1) in _SAFE_ENV_VARS)
