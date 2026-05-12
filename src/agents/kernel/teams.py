from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps
from agents.kernel.specs import AgentSpec


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    name: str
    description: str = ""
    members: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    workspace_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        spec: AgentSpec,
        team_id: str,
        name: str,
        description: str = "",
        members: dict[str, dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "TeamRecord":
        resolved = spec.with_workspace_defaults()
        return cls(
            team_id=safe_team_id(team_id),
            name=str(name or team_id),
            description=str(description or ""),
            members={str(key): dict(value) for key, value in dict(members or {}).items()},
            agent_id=resolved.agent_id or resolved.workspace.agent_id,
            tenant_id=resolved.workspace.tenant_id,
            user_id=resolved.workspace.user_id,
            workspace_id=resolved.workspace.workspace_id,
            metadata=dict(metadata or {}),
        )

    def with_update(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        members: dict[str, dict[str, Any]] | None = None,
    ) -> "TeamRecord":
        return replace(
            self,
            name=self.name if name is None else str(name),
            description=self.description if description is None else str(description),
            members=self.members if members is None else {str(key): dict(value) for key, value in members.items()},
            updated_at=time.time(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "description": self.description,
            "members": {key: dict(value) for key, value in self.members.items()},
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TeamMessageRecord:
    message_id: str
    team_id: str
    from_agent: str
    to_agent: str
    message: str
    message_type: str = "message"
    read: bool = False
    agent_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    workspace_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        spec: AgentSpec,
        team_id: str,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str = "message",
        metadata: dict[str, str] | None = None,
    ) -> "TeamMessageRecord":
        resolved = spec.with_workspace_defaults()
        return cls(
            message_id="teammsg_%s" % uuid4().hex[:12],
            team_id=safe_team_id(team_id),
            from_agent=safe_agent_id(from_agent),
            to_agent=safe_agent_id(to_agent),
            message=str(message or ""),
            message_type=str(message_type or "message"),
            agent_id=resolved.agent_id or resolved.workspace.agent_id,
            tenant_id=resolved.workspace.tenant_id,
            user_id=resolved.workspace.user_id,
            workspace_id=resolved.workspace.workspace_id,
            metadata=dict(metadata or {}),
        )

    def mark_read(self) -> "TeamMessageRecord":
        return replace(self, read=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "team_id": self.team_id,
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.message_type,
            "message": self.message,
            "created_at": self.created_at,
            "read": self.read,
            "metadata": dict(self.metadata),
        }


class TeamStore(Protocol):
    async def save_team(self, team: TeamRecord) -> None:
        raise NotImplementedError()

    async def load_team(
        self,
        team_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TeamRecord]:
        raise NotImplementedError()

    async def list_teams(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TeamRecord]:
        raise NotImplementedError()

    async def add_message(self, message: TeamMessageRecord) -> None:
        raise NotImplementedError()

    async def list_messages(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
        team_id: str = "",
        to_agent: str = "",
        unread_only: bool = True,
        limit: int = 50,
    ) -> List[TeamMessageRecord]:
        raise NotImplementedError()

    async def mark_messages_read(self, message_ids: list[str]) -> None:
        raise NotImplementedError()


class InMemoryTeamStore:
    def __init__(self):
        self._teams: Dict[tuple[str, str, str, str, str], TeamRecord] = {}
        self._messages: Dict[str, TeamMessageRecord] = {}

    async def save_team(self, team: TeamRecord) -> None:
        self._teams[_team_key(team)] = team.with_update()

    async def load_team(
        self,
        team_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TeamRecord]:
        resolved = safe_team_id(team_id)
        for team in self._teams.values():
            if team.team_id == resolved and _team_matches(team, tenant_id, user_id, agent_id, workspace_id):
                return team
        return None

    async def list_teams(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TeamRecord]:
        return sorted(
            [team for team in self._teams.values() if _team_matches(team, tenant_id, user_id, agent_id, workspace_id)],
            key=lambda team: (team.updated_at, team.team_id),
            reverse=True,
        )

    async def add_message(self, message: TeamMessageRecord) -> None:
        self._messages[message.message_id] = message

    async def list_messages(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
        team_id: str = "",
        to_agent: str = "",
        unread_only: bool = True,
        limit: int = 50,
    ) -> List[TeamMessageRecord]:
        selected = [
            message
            for message in self._messages.values()
            if _message_matches(message, tenant_id, user_id, agent_id, workspace_id, team_id, to_agent, unread_only)
        ]
        selected = sorted(selected, key=lambda message: (message.created_at, message.message_id))
        return selected[-_limit(limit) :]

    async def mark_messages_read(self, message_ids: list[str]) -> None:
        for message_id in message_ids:
            message = self._messages.get(message_id)
            if message is not None:
                self._messages[message_id] = message.mark_read()


class SQLiteTeamStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save_team(self, team: TeamRecord) -> None:
        record = team.with_update()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO teams (
                    team_id, name, description, agent_id, tenant_id, user_id,
                    workspace_id, members_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id, agent_id, workspace_id, team_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    agent_id = excluded.agent_id,
                    tenant_id = excluded.tenant_id,
                    user_id = excluded.user_id,
                    workspace_id = excluded.workspace_id,
                    members_json = excluded.members_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.team_id,
                    record.name,
                    record.description,
                    record.agent_id,
                    record.tenant_id,
                    record.user_id,
                    record.workspace_id,
                    json_dumps(record.members),
                    json_dumps(record.metadata),
                    record.created_at,
                    record.updated_at,
                ),
            )

    async def load_team(
        self,
        team_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TeamRecord]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM teams
                WHERE team_id = ?
                  AND tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                """,
                (safe_team_id(team_id), tenant_id, user_id, agent_id, workspace_id),
            ).fetchone()
        return _team_from_row(row) if row is not None else None

    async def list_teams(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TeamRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM teams
                WHERE tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                ORDER BY updated_at DESC, team_id ASC
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            ).fetchall()
        return [_team_from_row(row) for row in rows]

    async def add_message(self, message: TeamMessageRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO team_messages (
                    message_id, team_id, from_agent, to_agent, message_type, message,
                    read, agent_id, tenant_id, user_id, workspace_id, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.team_id,
                    message.from_agent,
                    message.to_agent,
                    message.message_type,
                    message.message,
                    1 if message.read else 0,
                    message.agent_id,
                    message.tenant_id,
                    message.user_id,
                    message.workspace_id,
                    json_dumps(message.metadata),
                    message.created_at,
                ),
            )

    async def list_messages(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
        team_id: str = "",
        to_agent: str = "",
        unread_only: bool = True,
        limit: int = 50,
    ) -> List[TeamMessageRecord]:
        query = """
            SELECT * FROM team_messages
            WHERE tenant_id = ?
              AND (user_id = '' OR user_id = ?)
              AND (agent_id = '' OR agent_id = ?)
              AND (workspace_id = '' OR workspace_id = ?)
              AND (? = '' OR team_id = ?)
              AND (? = '' OR to_agent = ?)
              AND (? = 0 OR read = 0)
            ORDER BY created_at DESC, message_id DESC
            LIMIT ?
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                query,
                (
                    tenant_id,
                    user_id,
                    agent_id,
                    workspace_id,
                    safe_team_id(team_id) if team_id else "",
                    safe_team_id(team_id) if team_id else "",
                    safe_agent_id(to_agent) if to_agent else "",
                    safe_agent_id(to_agent) if to_agent else "",
                    1 if unread_only else 0,
                    _limit(limit),
                ),
            ).fetchall()
        return list(reversed([_message_from_row(row) for row in rows]))

    async def mark_messages_read(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        placeholders = ", ".join("?" for _ in message_ids)
        with self.database.connect() as connection:
            connection.execute("UPDATE team_messages SET read = 1 WHERE message_id IN (%s)" % placeholders, tuple(message_ids))


def safe_team_id(value: Any) -> str:
    return safe_token(value) or "default"


def safe_agent_id(value: Any) -> str:
    return safe_token(value)


def safe_token(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")


def _team_key(team: TeamRecord) -> tuple[str, str, str, str, str]:
    return (team.tenant_id, team.user_id, team.agent_id, team.workspace_id, team.team_id)


def _team_matches(team: TeamRecord, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        team.tenant_id == tenant_id
        and team.user_id in ("", user_id)
        and team.agent_id in ("", agent_id)
        and team.workspace_id in ("", workspace_id)
    )


def _message_matches(
    message: TeamMessageRecord,
    tenant_id: str,
    user_id: str,
    agent_id: str,
    workspace_id: str,
    team_id: str,
    to_agent: str,
    unread_only: bool,
) -> bool:
    return (
        message.tenant_id == tenant_id
        and message.user_id in ("", user_id)
        and message.agent_id in ("", agent_id)
        and message.workspace_id in ("", workspace_id)
        and (not team_id or message.team_id == safe_team_id(team_id))
        and (not to_agent or message.to_agent == safe_agent_id(to_agent))
        and (not unread_only or not message.read)
    )


def _team_from_row(row) -> TeamRecord:
    return TeamRecord(
        team_id=str(row["team_id"]),
        name=str(row["name"]),
        description=str(row["description"] or ""),
        members={str(key): dict(value) for key, value in json_dict(row["members_json"]).items()},
        agent_id=str(row["agent_id"] or ""),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _message_from_row(row) -> TeamMessageRecord:
    return TeamMessageRecord(
        message_id=str(row["message_id"]),
        team_id=str(row["team_id"]),
        from_agent=str(row["from_agent"] or ""),
        to_agent=str(row["to_agent"] or ""),
        message_type=str(row["message_type"] or "message"),
        message=str(row["message"] or ""),
        read=bool(int(row["read"])),
        agent_id=str(row["agent_id"] or ""),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
    )


def _limit(limit: int) -> int:
    return max(1, min(int(limit or 50), 100))
