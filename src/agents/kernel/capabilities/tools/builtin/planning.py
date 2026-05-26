from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.session_state import save_session_state


TODO_STATUS_VALUES = ["pending", "in_progress", "completed"]

TODO_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "Imperative task description, for example Run tests."},
        "status": {"type": "string", "enum": TODO_STATUS_VALUES},
        "activeForm": {"type": "string", "description": "Present-continuous form, for example Running tests."},
    },
    "required": ["content", "status", "activeForm"],
    "additionalProperties": False,
}

TODO_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "items": TODO_ITEM_SCHEMA,
            "description": "The full updated todo list for the current session.",
        }
    },
    "required": ["todos"],
    "additionalProperties": False,
}

TODO_READ_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

TODO_WRITE_RESULT_MESSAGE = (
    "Todos have been modified successfully. "
    "Ensure that you continue to use the todo list to track your progress. "
    "Please proceed with the current tasks if applicable"
)
TODO_VERIFICATION_NUDGE = (
    "\n\nNOTE: You just closed out 3+ tasks and none of them was a verification step. "
    'Before writing your final summary, spawn the verification agent (subagent_type="verification").'
)

PLAN_ENTER_SCHEMA = {
    "type": "object",
    "properties": {},
}

SRC_ORIGIN_PLAN_ENTER_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

PLAN_STATUS_SCHEMA = {
    "type": "object",
    "properties": {},
}

PLAN_EXIT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {"type": "string", "description": "Concrete implementation plan to present before coding."},
        "allowedPrompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["tool", "prompt"],
                "additionalProperties": False,
            },
            "description": "Optional semantic permissions requested by the plan.",
        },
    },
    "required": ["plan"],
}

SRC_ORIGIN_PLAN_EXIT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {"type": "string", "description": "Concrete implementation plan to present before coding."},
        "allowedPrompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["tool", "prompt"],
                "additionalProperties": False,
            },
            "description": "Prompt-based permissions requested by the plan.",
        },
        "planFilePath": {"type": "string", "description": "Optional plan file path supplied by SDK normalization."},
    },
    "required": ["plan"],
    "additionalProperties": False,
}


async def todo_write(context: ToolRuntimeContext, todos: list[dict[str, Any]]) -> dict[str, Any]:
    old_todos = [dict(item) for item in context.todos]
    new_todos = _normalize_todos(todos)
    all_done = all(item["status"] == "completed" for item in new_todos)
    context.todos = [] if all_done else [dict(item) for item in new_todos]
    await persist_planning_state(context)
    return {
        "oldTodos": old_todos,
        "newTodos": new_todos,
        "verificationNudgeNeeded": False,
        "activeTodos": [dict(item) for item in context.todos],
        "cleared": all_done,
        "summary": _todo_summary(context.todos),
    }


async def todo_read(context: ToolRuntimeContext) -> dict[str, Any]:
    return {
        "todos": [dict(item) for item in context.todos],
        "summary": _todo_summary(context.todos),
    }


async def plan_enter(context: ToolRuntimeContext) -> dict[str, Any]:
    context.plan_mode = True
    await persist_planning_state(context)
    return {
        "mode": "plan",
        "message": (
            "Entered plan mode. Explore and design the approach without editing files, then call plan.exit "
            "with the implementation plan when ready."
        ),
    }


async def src_origin_plan_enter(context: ToolRuntimeContext) -> dict[str, Any]:
    result = await plan_enter(context)
    return {
        **result,
        "message": "Entered plan mode. You should now focus on exploring the codebase and designing an implementation approach.",
    }


async def plan_status(context: ToolRuntimeContext) -> dict[str, Any]:
    return {
        "mode": "plan" if context.plan_mode else "default",
        "plan": context.plan_text,
        "allowedPrompts": [dict(item) for item in context.plan_allowed_prompts],
        "todos": [dict(item) for item in context.todos],
    }


async def plan_exit(
    context: ToolRuntimeContext,
    plan: str,
    allowedPrompts: list[dict[str, Any]] | None = None,
    allowed_prompts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not context.plan_mode:
        raise RuntimeError("not in plan mode")
    text = _required_text(plan, "plan")
    prompts = _normalize_allowed_prompts(allowedPrompts if allowedPrompts is not None else allowed_prompts)
    context.plan_mode = False
    context.plan_text = text
    context.plan_allowed_prompts = prompts
    await persist_planning_state(context)
    return {
        "mode": "default",
        "plan": text,
        "allowedPrompts": [dict(item) for item in prompts],
        "message": "Exited plan mode. Continue only after the plan is accepted by the caller or approval policy.",
    }


async def src_origin_plan_exit(
    context: ToolRuntimeContext,
    plan: str,
    allowedPrompts: list[dict[str, Any]] | None = None,
    planFilePath: str | None = None,
) -> dict[str, Any]:
    result = await plan_exit(context, plan=plan, allowedPrompts=allowedPrompts)
    payload = {
        **result,
        "isAgent": bool(context.subagent_depth or context.current_task_id),
    }
    file_path = str(planFilePath or "").strip()
    if file_path:
        payload["filePath"] = file_path
    return payload


async def plan_clear(context: ToolRuntimeContext) -> dict[str, Any]:
    context.plan_mode = False
    context.plan_text = ""
    context.plan_allowed_prompts = []
    await persist_planning_state(context)
    return {
        "mode": "default",
        "plan": "",
        "allowedPrompts": [],
        "message": "Cleared plan mode state.",
    }


async def persist_planning_state(context: ToolRuntimeContext) -> None:
    store = getattr(context, "session_state_store", None)
    if store is None:
        return
    await save_session_state(context)


def _normalize_todos(todos: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(todos, list):
        raise TypeError("todos must be a list")
    result = [_normalize_todo(item) for item in todos]
    in_progress = [item for item in result if item["status"] == "in_progress"]
    if len(in_progress) > 1:
        raise ValueError("only one todo can be in_progress")
    return result


def _normalize_todo(item: dict[str, Any]) -> dict[str, str]:
    if not isinstance(item, dict):
        raise TypeError("todo items must be objects")
    content = _required_text(item.get("content"), "content")
    active_form = _required_text(item.get("activeForm", item.get("active_form")), "activeForm")
    status = str(item.get("status") or "").strip()
    if status not in TODO_STATUS_VALUES:
        raise ValueError("unknown todo status: %s" % status)
    return {"content": content, "status": status, "activeForm": active_form}


def _normalize_allowed_prompts(prompts: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    result = []
    for item in list(prompts or []):
        if not isinstance(item, dict):
            raise TypeError("allowedPrompts items must be objects")
        result.append(
            {
                "tool": _required_text(item.get("tool"), "tool"),
                "prompt": _required_text(item.get("prompt"), "prompt"),
            }
        )
    return result


def _todo_summary(todos: list[dict[str, str]]) -> dict[str, int]:
    return {status: len([item for item in todos if item.get("status") == status]) for status in TODO_STATUS_VALUES}


def format_todo_write_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    if payload.get("verificationNudgeNeeded"):
        return TODO_WRITE_RESULT_MESSAGE + TODO_VERIFICATION_NUDGE
    return TODO_WRITE_RESULT_MESSAGE


def format_src_origin_plan_enter_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    message = str(payload.get("message") or "Entered plan mode.")
    return (
        f"{message}\n\n"
        "In plan mode, you should:\n"
        "1. Thoroughly explore the codebase to understand existing patterns\n"
        "2. Identify similar features and architectural approaches\n"
        "3. Consider multiple approaches and their trade-offs\n"
        "4. Use AskUserQuestion if you need to clarify the approach\n"
        "5. Design a concrete implementation strategy\n"
        "6. When ready, use ExitPlanMode to present your plan for approval\n\n"
        "Remember: DO NOT write or edit any files yet. This is a read-only exploration and planning phase."
    )


def format_src_origin_plan_exit_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    if payload.get("awaitingLeaderApproval"):
        return _format_plan_approval_request(payload)
    if payload.get("isAgent"):
        return 'User has approved the plan. There is nothing else needed from you now. Please respond with "ok"'
    plan = str(payload.get("plan") or "").strip()
    if not plan:
        return "User has approved exiting plan mode. You can now proceed."
    lines = ["User has approved your plan. You can now start coding. Start with updating your todo list if applicable"]
    file_path = str(payload.get("filePath") or "").strip()
    if file_path:
        lines.extend(
            [
                "",
                f"Your plan has been saved to: {file_path}",
                "You can refer back to it if needed during implementation.",
            ]
        )
    if payload.get("hasTaskTool"):
        lines.append(
            "\nIf this plan can be broken down into multiple independent tasks, consider using the TeamCreate tool to create a team and parallelize the work."
        )
    plan_label = "Approved Plan (edited by user)" if payload.get("planWasEdited") else "Approved Plan"
    lines.extend(["", f"## {plan_label}:", plan])
    return "\n".join(lines)


def _format_plan_approval_request(payload: dict[str, Any]) -> str:
    file_path = str(payload.get("filePath") or "")
    request_id = str(payload.get("requestId") or "")
    return (
        "Your plan has been submitted to the team lead for approval.\n\n"
        f"Plan file: {file_path}\n\n"
        "**What happens next:**\n"
        "1. Wait for the team lead to review your plan\n"
        "2. You will receive a message in your inbox with approval/rejection\n"
        "3. If approved, you can proceed with implementation\n"
        "4. If rejected, refine your plan based on the feedback\n\n"
        "**Important:** Do NOT proceed until you receive approval. Check your inbox for response.\n\n"
        f"Request ID: {request_id}"
    )


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
