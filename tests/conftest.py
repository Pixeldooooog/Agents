from __future__ import annotations

import os
import tempfile
from pathlib import Path


_runtime_dir = tempfile.TemporaryDirectory(prefix="agents-test-runtime-")

os.environ["AGENT_DB_PATH"] = str(Path(_runtime_dir.name) / "agents.db")
