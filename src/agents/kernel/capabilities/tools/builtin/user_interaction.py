from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


ASK_USER_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "Questions to ask the user. Each question must have 2-4 options.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The complete question to ask the user."},
                    "header": {"type": "string", "description": "Very short label displayed as a chip or tag."},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                                "preview": {"type": "string"},
                            },
                            "required": ["label", "description"],
                            "additionalProperties": False,
                        },
                    },
                    "multiSelect": {"type": "boolean"},
                },
                "required": ["question", "header", "options"],
                "additionalProperties": False,
            },
        },
        "answers": {
            "type": "object",
            "description": "Answers collected by the approval/user-interaction UI, keyed by question text.",
            "additionalProperties": {"type": "string"},
        },
        "annotations": {
            "type": "object",
            "description": "Optional per-question annotations such as selected preview and notes.",
            "additionalProperties": True,
        },
        "metadata": {
            "type": "object",
            "description": "Optional tracking metadata.",
            "additionalProperties": True,
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}

USER_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The message for the user. Markdown is supported.",
        },
        "attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional file paths to attach, absolute or relative to the workspace.",
        },
        "status": {
            "type": "string",
            "enum": ["normal", "proactive"],
            "description": "normal for direct replies, proactive for unsolicited updates.",
        },
    },
    "required": ["message", "status"],
    "additionalProperties": False,
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"}


def ask_user_question(
    questions: list[dict[str, Any]],
    answers: dict[str, str] | None = None,
    annotations: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_questions = _normalize_questions(questions)
    payload: dict[str, Any] = {
        "questions": normalized_questions,
        "answers": {str(key): str(value) for key, value in dict(answers or {}).items()},
    }
    if annotations:
        payload["annotations"] = dict(annotations)
    if metadata:
        payload["metadata"] = dict(metadata)
    return payload


def format_ask_user_question_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    if not answers:
        return "User question is awaiting answers."
    lines = ["User answered questions:"]
    for question, answer in answers.items():
        lines.append("- %s -> %s" % (question, answer))
    return "\n".join(lines)


def send_user_message(
    context: ToolRuntimeContext,
    message: str,
    attachments: list[str] | None = None,
    status: str = "normal",
) -> dict[str, Any]:
    text = _required_text(message, "message")
    normalized_status = str(status or "normal").strip()
    if normalized_status not in {"normal", "proactive"}:
        raise ValueError("status must be normal or proactive")
    payload: dict[str, Any] = {
        "message": text,
        "status": normalized_status,
        "sentAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    resolved = _resolve_attachments(context, attachments or [])
    if resolved:
        payload["attachments"] = resolved
    return payload


def format_user_message_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    count = len(payload.get("attachments") or []) if isinstance(payload.get("attachments"), list) else 0
    suffix = "" if count == 0 else " (%d %s included)" % (count, "attachment" if count == 1 else "attachments")
    return "Message delivered to user.%s" % suffix


def _normalize_questions(questions: Any) -> list[dict[str, Any]]:
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")
    if not 1 <= len(questions) <= 4:
        raise ValueError("questions must include 1-4 items")
    normalized: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("question items must be objects")
        question = _required_text(item.get("question"), "question")
        if question in seen_questions:
            raise ValueError("Question texts must be unique")
        seen_questions.add(question)
        options = _normalize_options(item.get("options"), question)
        normalized.append(
            {
                "question": question,
                "header": _required_text(item.get("header"), "header"),
                "options": options,
                "multiSelect": bool(item.get("multiSelect", False)),
            }
        )
    return normalized


def _normalize_options(options: Any, question: str) -> list[dict[str, str]]:
    if not isinstance(options, list):
        raise ValueError("options must be a list")
    if not 2 <= len(options) <= 4:
        raise ValueError("question %s must include 2-4 options" % question)
    normalized: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("option items must be objects")
        label = _required_text(option.get("label"), "option.label")
        if label in seen_labels:
            raise ValueError("option labels must be unique within each question")
        seen_labels.add(label)
        payload = {
            "label": label,
            "description": _required_text(option.get("description"), "option.description"),
        }
        preview = str(option.get("preview") or "")
        if preview:
            payload["preview"] = preview
        normalized.append(payload)
    return normalized


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _resolve_attachments(context: ToolRuntimeContext, attachments: list[str]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for raw_path in attachments:
        path = _required_text(raw_path, "attachment")
        file_path = context.sandbox.resolve_workspace_path(path)
        if not file_path.exists():
            raise FileNotFoundError("attachment not found: %s" % path)
        if not file_path.is_file():
            raise ValueError("attachment must be a file: %s" % path)
        relative = context.sandbox.relative_workspace_path(file_path)
        resolved.append(
            {
                "path": relative,
                "size": file_path.stat().st_size,
                "isImage": _is_image_path(file_path),
            }
        )
    return resolved


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS
