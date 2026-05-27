from __future__ import annotations


TASK_STATUS_VALUES = ["created", "running", "paused", "awaiting_approval", "finished", "error", "canceled"]


TASK_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short task title."},
        "input": {"type": "string", "description": "Task prompt or work item. Defaults to title."},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["title"],
}

TASK_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["", *TASK_STATUS_VALUES],
            "description": "Optional task status filter.",
        },
        "agent_id": {"type": "string", "description": "Optional agent id filter. Defaults to current agent."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

TASK_GET_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Task id or unambiguous short id."},
    },
    "required": ["task_id"],
}

TASK_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Task id or unambiguous short id."},
        "title": {"type": "string", "description": "Updated task title."},
        "input": {"type": "string", "description": "Updated task prompt or work item."},
        "status": {
            "type": "string",
            "enum": TASK_STATUS_VALUES,
            "description": "New task status.",
        },
        "metadata": {
            "type": "object",
            "description": "Metadata keys to merge. Null values delete keys.",
            "additionalProperties": True,
        },
    },
    "required": ["task_id"],
}

TASK_STOP_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Task id or unambiguous short id."},
    },
    "required": ["task_id"],
}

TASK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Task id or unambiguous short id."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
    "required": ["task_id"],
}

SRC_ORIGIN_TASK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The task ID to get output from."},
        "block": {"type": "boolean", "description": "Whether to wait for completion."},
        "timeout": {"type": "number", "minimum": 0, "maximum": 600000, "description": "Max wait time in milliseconds."},
    },
    "required": ["task_id"],
    "additionalProperties": False,
}

SRC_ORIGIN_TASK_STOP_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The ID of the background task to stop."},
        "shell_id": {"type": "string", "description": "Deprecated shell task id alias."},
    },
    "additionalProperties": False,
}

SRC_ORIGIN_TASK_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "A brief title for the task."},
        "description": {"type": "string", "description": "What needs to be done."},
        "activeForm": {"type": "string", "description": "Present-continuous status label."},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["subject", "description"],
    "additionalProperties": False,
}

SRC_ORIGIN_TASK_LIST_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

SRC_ORIGIN_TASK_GET_SCHEMA = {
    "type": "object",
    "properties": {
        "taskId": {"type": "string", "description": "The task ID to get."},
    },
    "required": ["taskId"],
    "additionalProperties": False,
}

SRC_ORIGIN_TASK_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "taskId": {"type": "string", "description": "The ID of the task to update."},
        "subject": {"type": "string", "description": "New subject for the task."},
        "description": {"type": "string", "description": "New description for the task."},
        "activeForm": {"type": "string", "description": "Present-continuous status label."},
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "deleted"],
            "description": "New src-origin task status.",
        },
        "owner": {"type": "string"},
        "addBlocks": {"type": "array", "items": {"type": "string"}},
        "addBlockedBy": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["taskId"],
    "additionalProperties": False,
}

TASK_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "Existing task id or unambiguous short id. If omitted, title/input create a new task first.",
        },
        "title": {"type": "string", "description": "Title for a new task when task_id is omitted."},
        "input": {"type": "string", "description": "Prompt/work item for a new task when task_id is omitted."},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
        "step_name": {"type": "string", "description": "Name for the execution step. Defaults to execute."},
    },
}

TASK_BACKGROUND_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "Existing task id or unambiguous short id. If omitted, title/input create a new task first.",
        },
        "title": {"type": "string", "description": "Title for a new task when task_id is omitted."},
        "input": {"type": "string", "description": "Prompt/work item for a new task when task_id is omitted."},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
        "step_name": {"type": "string", "description": "Name for the execution step. Defaults to execute."},
    },
}

TASK_BACKGROUNDS_SCHEMA = {
    "type": "object",
    "properties": {},
}
