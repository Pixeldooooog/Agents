from __future__ import annotations

import json
from typing import Any


def csv_setting(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def merge_unique(*groups: list[str]) -> list[str]:
    names: list[str] = []
    seen = set()
    for group in groups:
        for name in group:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def config_override_value(overrides: dict[str, str], setting: str) -> Any | None:
    raw = overrides.get("config.%s" % setting)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw
