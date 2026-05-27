from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.commands import (
    COMMAND_DELETE_SCHEMA,
    COMMAND_DISCOVER_SCHEMA,
    COMMAND_READ_SCHEMA,
    COMMAND_RENDER_SCHEMA,
    COMMAND_SAVE_SCHEMA,
    command_delete,
    command_discover,
    command_read,
    command_render,
    command_save,
)
from agents.kernel.capabilities.tools.builtin.extensions import (
    EXTENSION_NAME_SCHEMA,
    SKILL_INSTALL_SCHEMA,
    SKILL_UNINSTALL_SCHEMA,
    plugin_disable,
    plugin_enable,
    skill_disable,
    skill_install,
    skill_uninstall,
    skill_use,
)
from agents.kernel.capabilities.tools.builtin.meta import (
    SKILL_DISCOVER_SCHEMA,
    TOOL_SEARCH_SCHEMA,
    skill_discover,
    tool_search,
)
from agents.kernel.capabilities.tools.builtin.plugins import (
    PLUGIN_DISCOVER_SCHEMA,
    PLUGIN_INSTALL_SCHEMA,
    PLUGIN_UNINSTALL_SCHEMA,
    plugin_discover,
    plugin_install,
    plugin_uninstall,
)
from agents.kernel.capabilities.tools.builtin.prompts import (
    PROMPT_DELETE_SCHEMA,
    PROMPT_READ_SCHEMA,
    PROMPT_RENDER_SCHEMA,
    PROMPT_SAVE_SCHEMA,
    PROMPT_TEMPLATES_SCHEMA,
    prompt_delete,
    prompt_read,
    prompt_render,
    prompt_save,
    prompt_templates,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_command_and_extension_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_commands(registry, context)
    _register_meta(registry, context)
    _register_plugins(registry, context)
    _register_extension_management(registry, context)


def register_prompt_template_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "prompt.templates",
        "List local prompt templates in .agents/prompts.",
        PROMPT_TEMPLATES_SCHEMA,
        lambda query="", max_results=50: prompt_templates(context, query=query, max_results=max_results),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.read",
        "Read a local prompt template from .agents/prompts.",
        PROMPT_READ_SCHEMA,
        lambda name, max_bytes=20000: prompt_read(context, name=name, max_bytes=max_bytes),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.render",
        "Render a local prompt template with named or raw arguments.",
        PROMPT_RENDER_SCHEMA,
        lambda name, arguments=None, raw_arguments="": prompt_render(
            context,
            name=name,
            arguments=arguments,
            raw_arguments=raw_arguments,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.save",
        "Save a local prompt template under .agents/prompts.",
        PROMPT_SAVE_SCHEMA,
        lambda name, content, overwrite=False: prompt_save(
            context,
            name=name,
            content=content,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "prompt.delete",
        "Delete a local prompt template under .agents/prompts.",
        PROMPT_DELETE_SCHEMA,
        lambda name: prompt_delete(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )


def _register_commands(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "command.discover",
        "Discover prompt-backed workspace commands in .agents/commands or commands.",
        COMMAND_DISCOVER_SCHEMA,
        lambda query="", max_results=50: command_discover(context, query=query, max_results=max_results),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.render",
        "Render a prompt-backed workspace command with argument text.",
        COMMAND_RENDER_SCHEMA,
        lambda name, arguments="": command_render(context, name=name, arguments=arguments),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.read",
        "Read a prompt-backed workspace command file.",
        COMMAND_READ_SCHEMA,
        lambda name, max_bytes=20000: command_read(context, name=name, max_bytes=max_bytes),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.save",
        "Save a prompt-backed workspace command under .agents/commands.",
        COMMAND_SAVE_SCHEMA,
        lambda name,
        content,
        description="",
        argument_hint="",
        aliases=None,
        category="custom",
        overwrite=False: command_save(
            context,
            name=name,
            content=content,
            description=description,
            argument_hint=argument_hint,
            aliases=aliases,
            category=category,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "command.delete",
        "Delete a prompt-backed workspace command.",
        COMMAND_DELETE_SCHEMA,
        lambda name: command_delete(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )


def _register_meta(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "tool.search",
        "Search the current tool catalog by name, description, or metadata.",
        TOOL_SEARCH_SCHEMA,
        lambda query="", max_results=20, include_all=False: tool_search(
            context,
            registry,
            query=query,
            max_results=max_results,
            include_all=include_all,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "skill.discover",
        "Discover available local skills and their tool/prompt contributions.",
        SKILL_DISCOVER_SCHEMA,
        lambda query="", max_results=20, include_prompt=False: skill_discover(
            context,
            query=query,
            max_results=max_results,
            include_prompt=include_prompt,
        ),
        metadata={"risk": "low", "model_call": True},
    )


def _register_plugins(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "plugin.discover",
        "Discover local plugins and their tool/prompt contributions in the current workspace.",
        PLUGIN_DISCOVER_SCHEMA,
        lambda query="", max_results=20, include_prompt=False: plugin_discover(
            context,
            query=query,
            max_results=max_results,
            include_prompt=include_prompt,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "plugin.install",
        "Install a local plugin directory into .agents/plugins.",
        PLUGIN_INSTALL_SCHEMA,
        lambda source: plugin_install(context, source=source),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.uninstall",
        "Uninstall an installed plugin from .agents/plugins by name.",
        PLUGIN_UNINSTALL_SCHEMA,
        lambda name: plugin_uninstall(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )


def _register_extension_management(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "skill.install",
        "Install a local skill JSON file or skill package directory into skills.",
        SKILL_INSTALL_SCHEMA,
        lambda source: skill_install(context, source=source),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.uninstall",
        "Uninstall a local skill from skills by name.",
        SKILL_UNINSTALL_SCHEMA,
        lambda name: skill_uninstall(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.use",
        "Enable a local skill for the current session, including prompt fragments and tool contributions.",
        EXTENSION_NAME_SCHEMA,
        lambda name: skill_use(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.disable",
        "Disable a previously enabled local skill's tool contributions for the current session.",
        EXTENSION_NAME_SCHEMA,
        lambda name: skill_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.enable",
        "Enable a local plugin for the current session, including prompt fragments and tool contributions.",
        EXTENSION_NAME_SCHEMA,
        lambda name: plugin_enable(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.disable",
        "Disable a previously enabled local plugin's tool contributions for the current session.",
        EXTENSION_NAME_SCHEMA,
        lambda name: plugin_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
