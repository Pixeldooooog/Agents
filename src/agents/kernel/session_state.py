from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Optional, Protocol

from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps, json_list


@dataclass(frozen=True)
class SessionStateRecord:
    tenant_id: str
    user_id: str = ""
    agent_id: str = ""
    workspace_id: str = ""
    todos: list[dict[str, str]] = field(default_factory=list)
    plan_mode: bool = False
    plan_text: str = ""
    plan_allowed_prompts: list[dict[str, str]] = field(default_factory=list)
    system_prompt_override: str = ""
    system_prompt_overridden: bool = False
    permission_profile_override: str = ""
    permission_mode_override: str = ""
    permission_restrict_allowed_tools: bool = False
    permission_allowed_tools_override: list[str] = field(default_factory=list)
    permission_denied_tools_override: list[str] = field(default_factory=list)
    approval_required_tools_override: list[str] = field(default_factory=list)
    permission_overridden: bool = False
    enabled_skills: list[str] = field(default_factory=list)
    enabled_plugins: list[str] = field(default_factory=list)
    skill_tools: dict[str, list[str]] = field(default_factory=dict)
    plugin_tools: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def with_update(self) -> "SessionStateRecord":
        return replace(self, updated_at=time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "todos": [dict(item) for item in self.todos],
            "plan_mode": self.plan_mode,
            "plan_text": self.plan_text,
            "plan_allowed_prompts": [dict(item) for item in self.plan_allowed_prompts],
            "system_prompt_override": self.system_prompt_override,
            "system_prompt_overridden": self.system_prompt_overridden,
            "permission_profile_override": self.permission_profile_override,
            "permission_mode_override": self.permission_mode_override,
            "permission_restrict_allowed_tools": self.permission_restrict_allowed_tools,
            "permission_allowed_tools_override": list(self.permission_allowed_tools_override),
            "permission_denied_tools_override": list(self.permission_denied_tools_override),
            "approval_required_tools_override": list(self.approval_required_tools_override),
            "permission_overridden": self.permission_overridden,
            "enabled_skills": list(self.enabled_skills),
            "enabled_plugins": list(self.enabled_plugins),
            "skill_tools": {key: list(value) for key, value in self.skill_tools.items()},
            "plugin_tools": {key: list(value) for key, value in self.plugin_tools.items()},
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStateStore(Protocol):
    async def save(self, record: SessionStateRecord) -> None:
        raise NotImplementedError()

    async def load_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[SessionStateRecord]:
        raise NotImplementedError()

    async def delete(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        raise NotImplementedError()


class InMemorySessionStateStore:
    def __init__(self):
        self._records: dict[tuple[str, str, str, str], SessionStateRecord] = {}

    async def save(self, record: SessionStateRecord) -> None:
        updated = record.with_update()
        self._records[_key(updated)] = updated

    async def load_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[SessionStateRecord]:
        matches = [
            record
            for record in self._records.values()
            if _matches(record, tenant_id, user_id, agent_id, workspace_id)
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda record: (_specificity(record), record.updated_at), reverse=True)[0]

    async def delete(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        self._records.pop((tenant_id, user_id, agent_id, workspace_id), None)


class SQLiteSessionStateStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save(self, record: SessionStateRecord) -> None:
        updated = record.with_update()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_states (
                    tenant_id, user_id, agent_id, workspace_id,
                    todos_json, plan_mode, plan_text, plan_allowed_prompts_json,
                    system_prompt_override, system_prompt_overridden,
                    permission_profile_override, permission_mode_override,
                    permission_restrict_allowed_tools, permission_allowed_tools_override_json,
                    permission_denied_tools_override_json,
                    approval_required_tools_override_json, permission_overridden,
                    enabled_skills_json, enabled_plugins_json, skill_tools_json, plugin_tools_json,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id, agent_id, workspace_id) DO UPDATE SET
                    todos_json = excluded.todos_json,
                    plan_mode = excluded.plan_mode,
                    plan_text = excluded.plan_text,
                    plan_allowed_prompts_json = excluded.plan_allowed_prompts_json,
                    system_prompt_override = excluded.system_prompt_override,
                    system_prompt_overridden = excluded.system_prompt_overridden,
                    permission_profile_override = excluded.permission_profile_override,
                    permission_mode_override = excluded.permission_mode_override,
                    permission_restrict_allowed_tools = excluded.permission_restrict_allowed_tools,
                    permission_allowed_tools_override_json = excluded.permission_allowed_tools_override_json,
                    permission_denied_tools_override_json = excluded.permission_denied_tools_override_json,
                    approval_required_tools_override_json = excluded.approval_required_tools_override_json,
                    permission_overridden = excluded.permission_overridden,
                    enabled_skills_json = excluded.enabled_skills_json,
                    enabled_plugins_json = excluded.enabled_plugins_json,
                    skill_tools_json = excluded.skill_tools_json,
                    plugin_tools_json = excluded.plugin_tools_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    updated.tenant_id,
                    updated.user_id,
                    updated.agent_id,
                    updated.workspace_id,
                    json_dumps(updated.todos),
                    1 if updated.plan_mode else 0,
                    updated.plan_text,
                    json_dumps(updated.plan_allowed_prompts),
                    updated.system_prompt_override,
                    1 if updated.system_prompt_overridden else 0,
                    updated.permission_profile_override,
                    updated.permission_mode_override,
                    1 if updated.permission_restrict_allowed_tools else 0,
                    json_dumps(updated.permission_allowed_tools_override),
                    json_dumps(updated.permission_denied_tools_override),
                    json_dumps(updated.approval_required_tools_override),
                    1 if updated.permission_overridden else 0,
                    json_dumps(updated.enabled_skills),
                    json_dumps(updated.enabled_plugins),
                    json_dumps(updated.skill_tools),
                    json_dumps(updated.plugin_tools),
                    json_dumps(updated.metadata),
                    updated.created_at,
                    updated.updated_at,
                ),
            )

    async def load_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[SessionStateRecord]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM session_states
                WHERE tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                ORDER BY
                    ((user_id != '') + (agent_id != '') + (workspace_id != '')) DESC,
                    updated_at DESC
                LIMIT 1
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            ).fetchone()
        return _record_from_row(row) if row is not None else None

    async def delete(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM session_states
                WHERE tenant_id = ?
                  AND user_id = ?
                  AND agent_id = ?
                  AND workspace_id = ?
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            )


def session_state_record_for_context(context: Any) -> SessionStateRecord:
    workspace = context.workspace
    return SessionStateRecord(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        todos=_string_dicts(getattr(context, "todos", []) or []),
        plan_mode=bool(getattr(context, "plan_mode", False)),
        plan_text=str(getattr(context, "plan_text", "") or ""),
        plan_allowed_prompts=_string_dicts(getattr(context, "plan_allowed_prompts", []) or []),
        system_prompt_override=str(getattr(context, "system_prompt_override", "") or ""),
        system_prompt_overridden=bool(getattr(context, "system_prompt_overridden", False)),
        permission_profile_override=str(getattr(context, "permission_profile_override", "") or ""),
        permission_mode_override=str(getattr(context, "permission_mode_override", "") or ""),
        permission_restrict_allowed_tools=bool(getattr(context, "permission_restrict_allowed_tools", False)),
        permission_allowed_tools_override=_string_list(getattr(context, "permission_allowed_tools_override", []) or []),
        permission_denied_tools_override=_string_list(getattr(context, "permission_denied_tools_override", []) or []),
        approval_required_tools_override=_string_list(getattr(context, "approval_required_tools_override", []) or []),
        permission_overridden=bool(getattr(context, "permission_overridden", False)),
        enabled_skills=_string_list(getattr(context, "enabled_skills", []) or []),
        enabled_plugins=_string_list(getattr(context, "enabled_plugins", []) or []),
        skill_tools=_string_list_mapping(getattr(context, "skill_tools", {}) or {}),
        plugin_tools=_string_list_mapping(getattr(context, "plugin_tools", {}) or {}),
    )


async def save_session_state(context: Any) -> None:
    store = getattr(context, "session_state_store", None)
    if store is None:
        return
    await store.save(session_state_record_for_context(context))


def _record_from_row(row) -> SessionStateRecord:
    return SessionStateRecord(
        tenant_id=str(row["tenant_id"]),
        user_id=str(row["user_id"] or ""),
        agent_id=str(row["agent_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        todos=_string_dicts(json_list(row["todos_json"])),
        plan_mode=bool(int(row["plan_mode"])),
        plan_text=str(row["plan_text"] or ""),
        plan_allowed_prompts=_string_dicts(json_list(row["plan_allowed_prompts_json"])),
        system_prompt_override=str(row["system_prompt_override"] or ""),
        system_prompt_overridden=bool(int(row["system_prompt_overridden"])),
        permission_profile_override=str(row["permission_profile_override"] or ""),
        permission_mode_override=str(row["permission_mode_override"] or ""),
        permission_restrict_allowed_tools=bool(int(row["permission_restrict_allowed_tools"])),
        permission_allowed_tools_override=_string_list(json_list(row["permission_allowed_tools_override_json"])),
        permission_denied_tools_override=_string_list(json_list(row["permission_denied_tools_override_json"])),
        approval_required_tools_override=_string_list(json_list(row["approval_required_tools_override_json"])),
        permission_overridden=bool(int(row["permission_overridden"])),
        enabled_skills=_string_list(json_list(row["enabled_skills_json"])),
        enabled_plugins=_string_list(json_list(row["enabled_plugins_json"])),
        skill_tools=_string_list_mapping(json_dict(row["skill_tools_json"])),
        plugin_tools=_string_list_mapping(json_dict(row["plugin_tools_json"])),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _key(record: SessionStateRecord) -> tuple[str, str, str, str]:
    return (record.tenant_id, record.user_id, record.agent_id, record.workspace_id)


def _matches(record: SessionStateRecord, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        record.tenant_id == tenant_id
        and record.user_id in ("", user_id)
        and record.agent_id in ("", agent_id)
        and record.workspace_id in ("", workspace_id)
    )


def _specificity(record: SessionStateRecord) -> int:
    return int(bool(record.user_id)) + int(bool(record.agent_id)) + int(bool(record.workspace_id))


def _string_dicts(items: list[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            result.append({str(key): str(value) for key, value in item.items()})
    return result


def _string_list(items: Any) -> list[str]:
    if isinstance(items, set):
        values = list(items)
    elif isinstance(items, list) or isinstance(items, tuple):
        values = list(items)
    else:
        values = []
    return sorted({str(item) for item in values if str(item)})


def _string_list_mapping(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, items in value.items():
        result[str(key)] = _string_list(items)
    return result
