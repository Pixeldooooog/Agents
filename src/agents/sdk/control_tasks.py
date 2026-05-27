from __future__ import annotations

from typing import Any

from agents.kernel.tasks import TaskEngine, TaskRecord
from agents.sdk.control import SDKControlStopTaskRequest
from agents.sdk.control_payloads import _sdk_task_payload, _task_id_matches, _task_in_sdk_scope
from agents.sdk.types import SDKOptions


class SDKControlTasksMixin:
    async def _stop_task_control_response(
        self,
        request: SDKControlStopTaskRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        task = await self._resolve_sdk_task(request.task_id, options)
        updated = await TaskEngine(self.persistence.tasks).cancel_task(task.task_id)
        return {"stopped": True, "task": _sdk_task_payload(updated)}

    async def _resolve_sdk_task(self, task_id: str, options: SDKOptions) -> TaskRecord:
        assert self.persistence is not None
        target = str(task_id or "").strip()
        if not target:
            raise ValueError("task_id is required")
        task = await self.persistence.tasks.load_task(target)
        if task is not None and _task_in_sdk_scope(task, options):
            return task
        matches = [
            task
            for task in await self.persistence.tasks.list_tasks(
                options.tenant_id or "",
                user_id=options.user_id or "",
                agent_id=options.agent_id or "",
            )
            if _task_id_matches(task.task_id, target)
        ]
        if not matches:
            raise KeyError("task not found: %s" % target)
        if len(matches) > 1:
            raise ValueError("task id is ambiguous: %s" % target)
        return matches[0]
