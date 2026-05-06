from __future__ import annotations

import os
from pathlib import Path

ROOT_PATH = str(Path(__file__).resolve().parents[4])

if os.environ.get("ENV_FILE"):
    ENV_FILE = os.environ["ENV_FILE"]
elif os.path.isfile(os.path.join(os.getcwd(), ".env")):
    ENV_FILE = os.path.join(os.getcwd(), ".env")
else:
    ENV_FILE = os.path.join(ROOT_PATH, ".env")
