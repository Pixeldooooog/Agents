from __future__ import annotations

from typing import Any

from agents.interfaces.server.api.agent.schemas import AgentTaskCreateRequest
from agents.interfaces.server.http import responses as resp
from agents.kernel.config import AgentConfigError
from agents.kernel.tasks import TaskRunner


async def create_task_response(persistence: Any, request_data: AgentTaskCreateRequest):
    spec = request_data.to_agent_spec()
    task = await persistence.tasks.create_task(
        spec,
        title=request_data.title or default_task_title(request_data.message),
        input=request_data.message,
        metadata=request_data.metadata,
    )
    return resp.ok(response=resp.Resp(data=task.to_dict()))


async def list_tasks_response(persistence: Any, tenant_id: str = "", user_id: str = "", agent_id: str = ""):
    tasks = await persistence.tasks.list_tasks(tenant_id, user_id=user_id, agent_id=agent_id)
    return resp.ok(response=resp.Resp(data={"tasks": [task.to_dict() for task in tasks]}))


async def get_task_response(persistence: Any, task_id: str):
    task = await persistence.tasks.load_task(task_id)
    if task is None:
        return resp.fail(resp.Resp(code="404", detail="task not found: %s" % task_id, http_status=404))
    steps = await persistence.tasks.list_steps(task_id)
    return resp.ok(
        response=resp.Resp(
            data={
                "task": task.to_dict(),
                "steps": [step.to_dict() for step in steps],
            }
        )
    )


async def run_task_response(persistence: Any, run_service: Any, session_factory: Any, task_id: str):
    task = await persistence.tasks.load_task(task_id)
    if task is None:
        return resp.fail(resp.Resp(code="404", detail="task not found: %s" % task_id, http_status=404))
    try:
        result = await TaskRunner(persistence.tasks, run_service, session_factory).run_task(task_id)
    except AgentConfigError as exc:
        return resp.fail(resp.Resp(code="400", detail={"task_id": task_id, "message": str(exc)}, http_status=400))
    except Exception as exc:  # noqa: BLE001 - task API must report persisted runner failures.
        return resp.fail(resp.Resp(code="500", detail={"task_id": task_id, "message": str(exc)}, http_status=500))
    return resp.ok(
        response=resp.Resp(
            data={
                "task": result.task.to_dict(),
                "step": result.step.to_dict(),
                "run": (await run_service.store.load_run(result.run.run_id) or result.run).to_dict(),
                "result": {
                    "status": result.result.status,
                    "content": result.result.content,
                    "events": [event.to_dict() for event in result.result.events],
                },
            }
        )
    )


async def cancel_task_response(persistence: Any, run_service: Any, session_factory: Any, task_id: str):
    task = await persistence.tasks.load_task(task_id)
    if task is None:
        return resp.fail(resp.Resp(code="404", detail="task not found: %s" % task_id, http_status=404))
    canceled = await TaskRunner(persistence.tasks, run_service, session_factory).cancel_task(task_id)
    return resp.ok(response=resp.Resp(data=canceled.to_dict()))


def default_task_title(message: str) -> str:
    text = " ".join(str(message or "").split())
    return text[:80] or "Untitled task"
