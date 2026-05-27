from __future__ import annotations

import base64
import json
from collections.abc import Mapping


def extract_bearer_token(headers: Mapping[str, str]) -> str | None:
    for key, value in headers.items():
        if key.lower() != "authorization" or not isinstance(value, str):
            continue
        prefix = "bearer "
        if value.lower().startswith(prefix):
            token = value[len(prefix) :].strip()
            return token or None
    return None


def decode_jwt_expiry(token: str | None) -> float | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}")
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    expiry = data.get("exp") if isinstance(data, dict) else None
    if isinstance(expiry, (int, float)):
        return float(expiry)
    return None
