from __future__ import annotations

from typing import Any

from agents.kernel.state.runs import RunRecord
from agents.sdk.control_payloads import _metadata_string_list, _sdk_system_message
from agents.sdk.event_fields import _text_field
from agents.sdk.file_rewind import _record_cwd
from agents.sdk.session_records import _runtime_fields_from_run
from agents.sdk.types import SDKOptions, SDKSystemMessage


class SDKControlSystemMessagesMixin:
    async def _system_message_from_session(
        self,
        session: Any,
        options: SDKOptions,
        *,
        session_id: str,
        run_id: str,
    ) -> SDKSystemMessage:
        workspace = getattr(session, "workspace", None)
        runtime = getattr(session, "runtime", None)
        mcp_servers = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=str(getattr(workspace, "tenant_id", "") or options.tenant_id or ""),
            user_id=str(getattr(workspace, "user_id", "") or options.user_id or ""),
            agent_id=str(getattr(workspace, "agent_id", "") or options.agent_id or ""),
            workspace_id=str(getattr(workspace, "workspace_id", "") or ""),
        )
        return _sdk_system_message(
            session_id=session_id,
            run_id=run_id,
            cwd=str(getattr(workspace, "path", "") or options.cwd or ""),
            model=str(getattr(runtime, "model", "") or options.model or ""),
            tools=[str(tool) for tool in list(getattr(runtime, "enabled_tools", []) or [])],
            skills=list(options.skills or []),
            permission_mode=options.permission_mode,
            metadata=options.metadata,
            mcp_servers=mcp_servers,
        )

    async def _system_message_from_run(self, record: RunRecord, *, session_id: str) -> SDKSystemMessage:
        model, _protocol, tools = _runtime_fields_from_run(record)
        spec = record.spec
        workspace = spec.get("workspace") if isinstance(spec.get("workspace"), dict) else {}
        spec_metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        metadata = {**dict(record.metadata), **dict(spec_metadata)}
        mcp_servers = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=_text_field(metadata, "sdk_tenant_id") or str(workspace.get("tenant_id") or ""),
            user_id=_text_field(metadata, "sdk_user_id") or str(workspace.get("user_id") or ""),
            agent_id=_text_field(metadata, "sdk_agent_id") or str(workspace.get("agent_id") or spec.get("agent_id") or ""),
            workspace_id=_text_field(metadata, "sdk_workspace_id") or str(workspace.get("workspace_id") or ""),
        )
        skills = spec.get("skills") if isinstance(spec.get("skills"), list) else []
        return _sdk_system_message(
            session_id=session_id,
            run_id=record.run_id,
            cwd=_record_cwd(record),
            model=_text_field(metadata, "sdk_init_model") or model,
            tools=_metadata_string_list(metadata, "sdk_init_tools_json") or tools,
            skills=[str(skill) for skill in skills],
            permission_mode=str(spec.get("permission_profile") or ""),
            metadata=metadata,
            mcp_servers=mcp_servers,
        )
