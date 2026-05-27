from __future__ import annotations

import re


def match_wildcard_pattern(pattern: str, command: str, *, case_insensitive: bool = False) -> bool:
    tokens = _wildcard_tokens(str(pattern or "").strip())
    wildcard_count = sum(1 for kind, _ in tokens if kind == "wildcard")
    if wildcard_count == 1 and len(tokens) >= 2 and tokens[-1][0] == "wildcard" and tokens[-2] == ("literal", " "):
        regex_pattern = _wildcard_regex(tokens[:-2]) + r"( .*)?"
    else:
        regex_pattern = _wildcard_regex(tokens)
    flags = re.DOTALL | (re.IGNORECASE if case_insensitive else 0)
    return re.match(r"^%s$" % regex_pattern, str(command or ""), flags) is not None


def find_first_unescaped(value: str, char: str) -> int:
    escaped = False
    for index, current in enumerate(value):
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == char:
            return index
    return -1


def find_last_unescaped(value: str, char: str) -> int:
    escaped = False
    result = -1
    for index, current in enumerate(value):
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == char:
            result = index
    return result


def unescape_rule_content(content: str) -> str:
    return content.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")


def _wildcard_tokens(pattern: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            next_char = pattern[index + 1]
            if next_char in {"*", "\\"}:
                tokens.append(("literal", next_char))
                index += 2
                continue
        if char == "*":
            tokens.append(("wildcard", char))
        else:
            tokens.append(("literal", char))
        index += 1
    return tokens


def _wildcard_regex(tokens: list[tuple[str, str]]) -> str:
    return "".join(".*" if kind == "wildcard" else re.escape(value) for kind, value in tokens)
