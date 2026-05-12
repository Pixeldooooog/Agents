from __future__ import annotations

import os
from pathlib import Path

def _discover_root_path() -> Path:
    override = os.environ.get("AGENTS_ROOT_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    module_path = Path(__file__).resolve()
    for candidate in [module_path.parent, *module_path.parents]:
        if (candidate / "config" / "defaults.toml").is_file():
            return candidate

    cwd = Path.cwd().resolve()
    if (cwd / "config" / "defaults.toml").is_file():
        return cwd

    # Keep a deterministic fallback for unusual packaging layouts.
    return module_path.parents[4]


ROOT_PATH = str(_discover_root_path())

if os.environ.get("ENV_FILE"):
    ENV_FILE = os.environ["ENV_FILE"]
elif os.path.isfile(os.path.join(os.getcwd(), ".env")):
    ENV_FILE = os.path.join(os.getcwd(), ".env")
else:
    ENV_FILE = os.path.join(ROOT_PATH, ".env")
