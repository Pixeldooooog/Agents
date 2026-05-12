from __future__ import annotations

import sqlite3
from pathlib import Path

from agents.kernel.persistence.schema import (
    APPROVAL_AUDIT_COLUMNS,
    RUNTIME_CHECKPOINT_COLUMNS,
    SANDBOX_EVENT_COLUMNS,
    SANDBOX_LEASE_COLUMNS,
    SCHEMA,
    SESSION_STATE_COLUMNS,
)


class SQLiteDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            _ensure_columns(connection, "runtime_checkpoints", RUNTIME_CHECKPOINT_COLUMNS)
            _ensure_columns(connection, "approval_audit", APPROVAL_AUDIT_COLUMNS)
            _ensure_columns(connection, "sandbox_leases", SANDBOX_LEASE_COLUMNS)
            _ensure_columns(connection, "sandbox_events", SANDBOX_EVENT_COLUMNS)
            _ensure_columns(connection, "session_states", SESSION_STATE_COLUMNS)


def resolve_database_path(root_path: Path, configured_path: str) -> Path:
    path = Path(configured_path or ".agents/agents.db")
    return path if path.is_absolute() else Path(root_path) / path


def _ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {str(row["name"]) for row in connection.execute("PRAGMA table_info(%s)" % table).fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, definition))
