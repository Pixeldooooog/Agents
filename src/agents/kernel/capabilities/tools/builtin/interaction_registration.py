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
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_interaction_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_structured_output(registry, context)
    _register_skill_invocation(registry, context)
    _register_config(registry, context)
    _register_user_interaction(registry, context)


def _agent_spec_metadata(context: ToolRuntimeContext) -> dict:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _register_structured_output(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    schema = structured_output_schema_from_metadata(_agent_spec_metadata(context))
    _register_builtin_tool(
        registry,
        name="structured.output",
        description="Return the final answer as structured data for SDK and non-interactive callers.",
        parameters=schema,
        handler=structured_output,
        metadata={"risk": "low", "structured_output": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="structured",
        activity_title="Structured output",
        result_formatter=format_structured_output_result,
    )


def _register_skill_invocation(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="skill.invoke",
        description="Invoke a local skill by expanding its prompt or executing it in a forked child agent.",
        parameters=SKILL_INVOKE_SCHEMA,
        handler=lambda skill, args="", mode="auto": skill_invoke(context, skill=skill, args=args, mode=mode),
        metadata={"risk": "high", "model_call": True},
        writes_state=False,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="skill",
        activity_title="Invoke skill",
        activity_target_argument="skill",
        result_formatter=format_skill_invoke_result,
    )


def _register_config(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="config.manage",
        description="Get or set session configuration settings such as theme, model, and permissions.defaultMode.",
        parameters=CONFIG_MANAGE_SCHEMA,
        handler=lambda setting, value=CONFIG_VALUE_UNSET: config_manage(context, setting=setting, value=value),
        metadata={"risk": "medium", "writes_state": True, "defer": True},
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Manage config",
        activity_target_argument="setting",
        result_formatter=format_config_result,
    )


def _register_user_interaction(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="user.message",
        description="Send a message to the user with optional workspace file attachments.",
        parameters=USER_MESSAGE_SCHEMA,
        handler=lambda message, attachments=None, status="normal": send_user_message(
            context,
            message=message,
            attachments=attachments,
            status=status,
        ),
        metadata={"risk": "low", "user_visible": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Message user",
        activity_target_argument="message",
        result_formatter=format_user_message_result,
    )
    _register_builtin_tool(
        registry,
        name="user.ask",
        description="Ask the user one or more multiple-choice questions and return their answers.",
        parameters=ASK_USER_QUESTION_SCHEMA,
        handler=lambda questions, answers=None, annotations=None, metadata=None: ask_user_question(
            questions=questions,
            answers=answers,
            annotations=annotations,
            metadata=metadata,
        ),
        metadata={"risk": "low", "requires_user_interaction": True, "defer": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Ask user",
        activity_target_argument="questions",
        result_formatter=format_ask_user_question_result,
    )
