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


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
