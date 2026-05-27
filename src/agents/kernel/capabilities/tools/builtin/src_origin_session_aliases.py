"""Registration wiring for src-origin session and user-facing aliases."""

from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.config import (
    CONFIG_MANAGE_SCHEMA,
    CONFIG_VALUE_UNSET,
    config_manage,
    format_config_result,
)
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.skill_invocation import (
    SKILL_INVOKE_SCHEMA,
    format_skill_invoke_result,
    skill_invoke,
)
from agents.kernel.capabilities.tools.builtin.structured import (
    format_structured_output_result,
    structured_output,
    structured_output_schema_from_metadata,
)
from agents.kernel.capabilities.tools.builtin.user_interaction import (
    ASK_USER_QUESTION_SCHEMA,
    USER_MESSAGE_SCHEMA,
    ask_user_question,
    format_ask_user_question_result,
    format_user_message_result,
    send_user_message,
)
from agents.kernel.capabilities.tools.builtin.worktree import (
    WORKTREE_ENTER_SCHEMA,
    WORKTREE_EXIT_SCHEMA,
    enter_worktree,
    exit_worktree,
    format_worktree_result,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_src_origin_session_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    structured_schema = structured_output_schema_from_metadata(_agent_spec_metadata(context))
    _register_builtin_tool(
        registry,
        name="StructuredOutput",
        description="Return structured output in the requested format. src-origin alias for structured.output.",
        parameters=structured_schema,
        handler=structured_output,
        metadata={"risk": "low", "structured_output": True, "alias_of": "structured.output", "src_origin_tool": "StructuredOutput"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="structured",
        activity_title="Structured output",
        result_formatter=format_structured_output_result,
    )
    _register_builtin_tool(
        registry,
        name="Skill",
        description="Invoke a slash-command skill. src-origin alias for skill.invoke.",
        parameters=SKILL_INVOKE_SCHEMA,
        handler=lambda skill, args="", mode="auto": skill_invoke(context, skill=skill, args=args, mode=mode),
        metadata={"risk": "high", "model_call": True, "alias_of": "skill.invoke", "src_origin_tool": "Skill"},
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="skill",
        activity_title="Invoke skill",
        activity_target_argument="skill",
        result_formatter=format_skill_invoke_result,
    )
    _register_builtin_tool(
        registry,
        name="Config",
        description="Get or set configuration settings. src-origin alias for config.manage.",
        parameters=CONFIG_MANAGE_SCHEMA,
        handler=lambda setting, value=CONFIG_VALUE_UNSET: config_manage(context, setting=setting, value=value),
        metadata={"risk": "medium", "writes_state": True, "defer": True, "alias_of": "config.manage", "src_origin_tool": "Config"},
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Manage config",
        activity_target_argument="setting",
        result_formatter=format_config_result,
    )
    _register_builtin_tool(
        registry,
        name="AskUserQuestion",
        description="Ask the user multiple-choice questions. src-origin alias for user.ask.",
        parameters=ASK_USER_QUESTION_SCHEMA,
        handler=lambda questions, answers=None, annotations=None, metadata=None: ask_user_question(
            questions=questions,
            answers=answers,
            annotations=annotations,
            metadata=metadata,
        ),
        metadata={"risk": "low", "requires_user_interaction": True, "defer": True, "alias_of": "user.ask", "src_origin_tool": "AskUserQuestion"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Ask user",
        activity_target_argument="questions",
        result_formatter=format_ask_user_question_result,
    )
    for alias_name in ("SendUserMessage", "Brief"):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Send a message to the user. src-origin alias for user.message.",
            parameters=USER_MESSAGE_SCHEMA,
            handler=lambda message, attachments=None, status="normal": send_user_message(
                context,
                message=message,
                attachments=attachments,
                status=status,
            ),
            metadata={"risk": "low", "user_visible": True, "alias_of": "user.message", "src_origin_tool": alias_name},
            read_only=True,
            max_result_size_chars=100000,
            activity_kind="state",
            activity_title="Message user",
            activity_target_argument="message",
            result_formatter=format_user_message_result,
        )
    _register_builtin_tool(
        registry,
        name="EnterWorktree",
        description="Create or resume an isolated git worktree. src-origin alias for worktree.enter.",
        parameters=WORKTREE_ENTER_SCHEMA,
        handler=lambda name="", pr_number=None, prNumber=None: enter_worktree(context, name=name, pr_number=pr_number, pr_number_alias=prNumber),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "worktree.enter", "src_origin_tool": "EnterWorktree"},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Enter worktree",
        activity_target_argument="name",
        result_formatter=format_worktree_result,
    )
    _register_builtin_tool(
        registry,
        name="ExitWorktree",
        description="Exit the active git worktree. src-origin alias for worktree.exit.",
        parameters=WORKTREE_EXIT_SCHEMA,
        handler=lambda action, discard_changes=False: exit_worktree(
            context,
            action=action,
            discard_changes=discard_changes,
        ),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "worktree.exit", "src_origin_tool": "ExitWorktree"},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Exit worktree",
        activity_target_argument="action",
        result_formatter=format_worktree_result,
    )


def _agent_spec_metadata(context: ToolRuntimeContext) -> dict:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}
