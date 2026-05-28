from __future__ import annotations

from agents.kernel.state import AgentProfile


def src_origin_profile_metadata(profile: AgentProfile) -> dict[str, object]:
    metadata = dict(profile.to_agent_spec().metadata)
    metadata.update(profile.metadata)
    return metadata


def metadata_value(metadata: dict[str, object], *keys: str) -> tuple[bool, object]:
    for key in keys:
        if key in metadata:
            return True, metadata[key]
    return False, None


def metadata_string_list(metadata: dict[str, object], *keys: str) -> tuple[str, ...]:
    found, value = metadata_value(metadata, *keys)
    if not found:
        return ()
    items = value if isinstance(value, (list, tuple, set)) else str(value or "").replace("\n", ",").split(",")
    return tuple(item for item in (str(item).strip() for item in items) if item)


def parse_src_origin_name_list(value: object) -> tuple[str, ...]:
    if value is None or value is False:
        return ()
    raw_items = value if isinstance(value, (list, tuple, set)) else [str(value)]
    parsed: list[str] = []
    for item in raw_items:
        parsed.extend(_parse_tool_list_item(str(item)))
    return tuple(parsed)


def parse_src_origin_tool_list(value: object) -> tuple[str, ...]:
    if value is None or value is False:
        return ()
    raw_items = value if isinstance(value, (list, tuple, set)) else [str(value)]
    parsed: list[str] = []
    for item in raw_items:
        parsed.extend(_parse_tool_list_item(str(item)))
    if "*" in parsed:
        return ("*",)
    return tuple(parsed)


def _parse_tool_list_item(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    paren_depth = 0
    for char in value:
        if char == "(":
            paren_depth += 1
            current.append(char)
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(char)
        elif (char == "," or char.isspace()) and paren_depth == 0:
            _push_tool_item(items, current)
        else:
            current.append(char)
    _push_tool_item(items, current)
    return items


def _push_tool_item(items: list[str], current: list[str]) -> None:
    value = "".join(current).strip()
    if value:
        items.append(value)
    current.clear()
