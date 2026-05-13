# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：routes.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agents.kernel.assembly import create_agent_session_async as _create_agent_session_async
from agents.kernel.governance.audit import ApprovalAuditRecord
from agents.kernel.config import AgentConfigError, active_profile_name, build_model_profiles, resolve_model_client_config
from agents.kernel.schema import RuntimeEvent
from agents.kernel.tasks import TaskStatus, TaskStepStatus
from agents.interfaces.server.api.agent.approval import (
    approval_bool_map,
    approval_grant_map,
    decision_map_from_request,
    new_runtime_events,
)
from agents.interfaces.server.api.agent.operation_frames import build_operation_frames
from agents.interfaces.server.api.agent.schemas import AgentChatRequest, AgentTaskCreateRequest, RunApprovalRequest
from agents.interfaces.server.api.agent.task_handlers import (
    cancel_task_response,
    create_task_response,
    get_task_response,
    list_tasks_response,
    run_task_response,
)
from agents.interfaces.server.core.config import settings
from agents.platform import create_durable_persistence
from agents.platform.sessions import (
    RunService,
    create_trace_recorder,
    run_created_event,
)
from agents.interfaces.server.http import responses as resp

router = APIRouter(prefix="/agent")

# 全局并发限制：同时处理的 agent 请求数
_agent_semaphore = asyncio.Semaphore(settings.agent.MAX_CONCURRENT_REQUESTS)
persistence = create_durable_persistence(settings)
trace_store = persistence.traces
run_service = RunService(
    persistence.runs,
    trace_recorder=create_trace_recorder(settings, trace_store),
    sandbox_store=persistence.sandboxes,
)
checkpoint_store = persistence.checkpoints
approval_audit_store = persistence.approval_audit


async def create_agent_session(**kwargs):
    return await _create_agent_session_async(
        settings,
        checkpoint_store=checkpoint_store,
        memory_store=persistence.memories,
        schedule_store=persistence.schedules,
        team_store=persistence.teams,
        hook_store=persistence.hooks,
        mcp_config_store=persistence.mcp_configs,
        session_state_store=persistence.session_states,
        sandbox_store=persistence.sandboxes,
        artifact_store=persistence.artifacts,
        artifact_blob_store=persistence.artifact_blobs,
        task_store=persistence.tasks,
        run_service=run_service,
        agent_profile_store=persistence.agent_profiles,
        **kwargs,
    )


class _TaskSessionFactory:
    async def create(self, task):
        return await create_agent_session(spec=task.to_agent_spec(), task_id=task.task_id)


@router.post("/chat")
async def chat(request_data: AgentChatRequest):
    async with _agent_semaphore:
        spec = request_data.to_agent_spec()
        run = await run_service.start(spec)
        session = None
        try:
            session = await create_agent_session(spec=spec)
            result = await session.send(request_data.message, run_id=run.run_id)
            await run_service.record_events(run.run_id, result.events)
            await _complete_or_pause(run.run_id, result.status, result.events)
        except AgentConfigError as exc:
            await _fail_run(run.run_id, "config", str(exc))
            return resp.fail(resp.Resp(code="400", detail={"run_id": run.run_id, "message": str(exc)}, http_status=400))
        except Exception as exc:  # noqa: BLE001 - server must persist failed run state before returning.
            await _fail_run(run.run_id, "runtime", str(exc))
            return resp.fail(resp.Resp(code="500", detail={"run_id": run.run_id, "message": str(exc)}, http_status=500))
        finally:
            await _close_session(session)
        return resp.ok(
            response=resp.Resp(
                data={
                    "run_id": run.run_id,
                    "status": result.status,
                    "content": result.content,
                    "messages": [message.to_dict() for message in result.messages],
                    "tool_results": [item.to_dict() for item in result.tool_results],
                    "events": [event.to_dict() for event in result.events],
                }
            )
        )


@router.post("/chat/stream")
async def chat_stream(request_data: AgentChatRequest):
    async def event_source():
        spec = request_data.to_agent_spec()
        run = None
        session = None
        try:
            run = await run_service.start(spec)
            yield _sse("run_created", run_created_event(run.run_id).to_dict())
            session = await create_agent_session(spec=spec)
            stream_error = ""
            approval_required = False
            async for event in session.stream(request_data.message, run_id=run.run_id):
                await run_service.record_event(run.run_id, event)
                if event.type == "done":
                    stream_error = str(event.payload.get("error") or "")
                    approval_required = event.payload.get("status") == "awaiting_approval"
                if event.type == "tool_approval_required":
                    approval_required = True
                yield _sse(event.type, event.to_dict())
            if approval_required:
                await run_service.pause_for_approval(run.run_id)
            else:
                await run_service.finish(run.run_id, stream_error)
        except Exception as exc:  # noqa: BLE001 - streams must report errors as events.
            if run is not None:
                await _fail_run(run.run_id, "runtime", str(exc))
            yield _sse("error", {"type": "error", "payload": {"message": str(exc)}})
        finally:
            await _close_session(session)

    # 流式请求的并发限制：获取 semaphore 后启动生成器
    await _agent_semaphore.acquire()

    async def _release_on_close():
        try:
            async for chunk in event_source():
                yield chunk
        finally:
            _agent_semaphore.release()

    return StreamingResponse(_release_on_close(), media_type="text/event-stream")


@router.get("/runs")
async def list_runs(limit: int = 50, tenant_id: str = "", user_id: str = "", agent_id: str = ""):
    records = await run_service.list_runs(limit=limit, tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
    return resp.ok(response=resp.Resp(data={"runs": [record.to_dict() for record in records]}))


@router.get("/model-profiles")
async def list_model_profiles():
    profiles = build_model_profiles(settings)
    active = ""
    try:
        configured = resolve_model_client_config(settings, api_key="configured")
        active = active_profile_name(profiles, configured.protocol, configured.model, configured.base_url)
    except AgentConfigError:
        active = ""
    return resp.ok(
        response=resp.Resp(
            data={
                "active_profile": active,
                "profiles": [
                    {
                        "name": profile.name,
                        "protocol": profile.protocol,
                        "model": profile.model,
                        "base_url": profile.base_url,
                        "endpoint": profile.endpoint,
                        "aliases": list(profile.aliases),
                        "source": profile.source,
                        "configured": profile.configured,
                    }
                    for profile in profiles
                ],
            }
        )
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    record = await run_service.store.load_run(run_id)
    if record is None:
        return resp.fail(resp.Resp(code="404", detail="run not found: %s" % run_id, http_status=404))
    return resp.ok(response=resp.Resp(data=record.to_dict()))


@router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: str):
    record = await run_service.store.load_run(run_id)
    if record is None:
        return resp.fail(resp.Resp(code="404", detail="run not found: %s" % run_id, http_status=404))
    spans = await trace_store.list_for_run(run_id)
    approvals = await approval_audit_store.list_for_run(run_id)
    sandbox_leases = await persistence.sandboxes.list_leases_for_run(run_id)
    sandbox_events = await persistence.sandboxes.list_events_for_run(run_id)
    sandbox_snapshots = await persistence.sandboxes.list_workspace_snapshots_for_run(run_id)
    artifacts = await persistence.artifacts.list_for_run(run_id)
    operation_frames = build_operation_frames(
        run_id=run_id,
        sandbox_events=sandbox_events,
        sandbox_snapshots=sandbox_snapshots,
        artifacts=[artifact.to_dict() for artifact in artifacts],
    )
    return resp.ok(
        response=resp.Resp(
            data={
                "run_id": run_id,
                "spans": [span.to_dict() for span in spans],
                "approvals": [approval.to_dict() for approval in approvals],
                "sandbox_leases": [lease.to_dict() for lease in sandbox_leases],
                "artifacts": [artifact.to_dict() for artifact in artifacts],
                "sandbox_events": [event.to_dict() for event in sandbox_events],
                "sandbox_snapshots": [snapshot.to_dict() for snapshot in sandbox_snapshots],
                "operation_frames": operation_frames,
            }
        )
    )


@router.post("/tasks")
async def create_task(request_data: AgentTaskCreateRequest):
    return await create_task_response(persistence, request_data)


@router.get("/tasks")
async def list_tasks(tenant_id: str = "", user_id: str = "", agent_id: str = ""):
    return await list_tasks_response(persistence, tenant_id, user_id=user_id, agent_id=agent_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    return await get_task_response(persistence, task_id)


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str):
    async with _agent_semaphore:
        return await run_task_response(persistence, run_service, _TaskSessionFactory(), task_id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    return await cancel_task_response(persistence, run_service, _TaskSessionFactory(), task_id)


@router.post("/runs/{run_id}/approval")
async def approve_run_tools(run_id: str, request_data: RunApprovalRequest):
    async with _agent_semaphore:
        record = await run_service.store.load_run(run_id)
        if record is None:
            return resp.fail(resp.Resp(code="404", detail="run not found: %s" % run_id, http_status=404))
        checkpoint = await checkpoint_store.load(run_id)
        if checkpoint is None or not checkpoint.pending_tool_calls:
            return resp.fail(resp.Resp(code="409", detail="run is not waiting for tool approval", http_status=409))

        try:
            approval_scopes = decision_map_from_request(request_data, checkpoint.pending_tool_calls)
            approvals = approval_bool_map(approval_scopes)
            approval_grants = approval_grant_map(checkpoint.pending_tool_calls, approvals, approval_scopes)
        except ValueError as exc:
            return resp.fail(resp.Resp(code="400", detail=str(exc), http_status=400))
        session = None
        try:
            await _record_approval_audit(run_id, request_data, checkpoint.pending_tool_calls, approvals, approval_scopes)
            await run_service.mark_running(run_id)
            session = await create_agent_session(spec=record.to_agent_spec())
            step = await persistence.tasks.load_step_for_run(run_id)
            result = await session.resume(
                run_id,
                approvals=approvals,
                approval_scopes=approval_scopes,
                approval_grants=approval_grants,
                task_id=step.task_id if step else None,
            )
            new_events = new_runtime_events(record.events, result.events)
            await run_service.record_events(run_id, new_events)
            await _complete_or_pause(run_id, result.status, new_events)
            await _sync_task_for_run(run_id, result.status, result.content, new_events)
        except AgentConfigError as exc:
            await _fail_run(run_id, "config", str(exc))
            return resp.fail(resp.Resp(code="400", detail={"run_id": run_id, "message": str(exc)}, http_status=400))
        except Exception as exc:  # noqa: BLE001 - approval resume must persist failed run state.
            await _fail_run(run_id, "runtime", str(exc))
            return resp.fail(resp.Resp(code="500", detail={"run_id": run_id, "message": str(exc)}, http_status=500))
        finally:
            await _close_session(session)
        return resp.ok(
            response=resp.Resp(
                data={
                    "run_id": run_id,
                    "status": result.status,
                    "content": result.content,
                    "messages": [message.to_dict() for message in result.messages],
                    "tool_results": [item.to_dict() for item in result.tool_results],
                    "events": [event.to_dict() for event in new_events],
                }
            )
        )


def _sse(event: str, data: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))


def _result_error(events) -> str:
    for event in events:
        if event.type == "error":
            return str(event.payload.get("message") or "runtime error")
    return ""


async def _complete_or_pause(run_id: str, status: str, events) -> None:
    if status == "awaiting_approval" or any(event.type == "tool_approval_required" for event in events):
        await run_service.pause_for_approval(run_id)
        return
    await run_service.finish(run_id, _result_error(events))


async def _sync_task_for_run(run_id: str, status: str, content: str, events) -> None:
    step = await persistence.tasks.load_step_for_run(run_id)
    if step is None:
        return
    if status == "awaiting_approval" or any(event.type == "tool_approval_required" for event in events):
        await persistence.tasks.update_step_status(step.step_id, TaskStepStatus.AWAITING_APPROVAL)
        await persistence.tasks.set_task_status(step.task_id, TaskStatus.AWAITING_APPROVAL)
        return
    error = _result_error(events)
    if error or status not in {"finished", ""}:
        await persistence.tasks.update_step_status(step.step_id, TaskStepStatus.FAILED, error=error or content)
        await persistence.tasks.set_task_status(step.task_id, TaskStatus.ERROR)
        return
    await persistence.tasks.update_step_status(step.step_id, TaskStepStatus.SUCCEEDED, output=content)
    await persistence.tasks.set_task_status(step.task_id, TaskStatus.FINISHED)


async def _fail_run(run_id: str, kind: str, message: str) -> None:
    await run_service.record_event(run_id, RuntimeEvent(type="error", name=kind, payload={"message": message}))
    await run_service.finish(run_id, message)


async def _record_approval_audit(
    run_id: str,
    request_data: RunApprovalRequest,
    pending_calls,
    approvals: dict[str, bool],
    decisions: dict[str, str],
) -> None:
    reason = request_data.reason or ""
    for call in pending_calls:
        approval_id = call.id or call.name
        if approval_id not in approvals:
            continue
        await approval_audit_store.record(
            ApprovalAuditRecord.from_tool_call(
                run_id=run_id,
                call=call,
                approved=approvals[approval_id],
                decision=decisions.get(approval_id, ""),
                reason=reason,
            )
        )


async def _close_session(session) -> None:
    if session is None:
        return
    close = getattr(session, "aclose", None)
    if close is not None:
        await close()
