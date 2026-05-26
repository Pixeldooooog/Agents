from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.mcp.ide import (
    IDE_DISCOVERY_SCHEMA,
    IDE_EXTENSION_SCHEMA,
    MCP_CONFIGURE_IDE_SCHEMA,
    mcp_configure_ide,
    mcp_detect_ide,
    mcp_ide_extension_status,
    mcp_install_ide_extension,
)
from agents.kernel.capabilities.tools.builtin.mcp.management import (
    MCP_CLEAR_SCHEMA,
    MCP_CONFIGURE_SCHEMA,
    MCP_RELOAD_SCHEMA,
    MCP_SERVER_NAME_SCHEMA,
    MCP_SERVERS_SCHEMA,
    mcp_clear,
    mcp_configure,
    mcp_disable,
    mcp_enable,
    mcp_remove,
    mcp_reconnect,
    mcp_reload,
    mcp_servers,
)
from agents.kernel.capabilities.tools.builtin.mcp.prompts import (
    MCP_GET_PROMPT_SCHEMA,
    MCP_PROMPTS_SCHEMA,
    mcp_get_prompt,
    mcp_prompts,
)
from agents.kernel.capabilities.tools.builtin.mcp.resources import (
    MCP_READ_RESOURCE_SCHEMA,
    MCP_RESOURCES_SCHEMA,
    mcp_read_resource,
    mcp_resources,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_mcp_builtin_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_mcp_management(registry, context)
    _register_mcp_prompts(registry, context)
    _register_mcp_resources(registry, context)


def _register_mcp_management(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.servers",
        "Read configured and loaded MCP server status.",
        MCP_SERVERS_SCHEMA,
        lambda: mcp_servers(context),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.configure",
        "Configure the local MCP server command for this session.",
        MCP_CONFIGURE_SCHEMA,
        lambda command="", name="default", transport="", url="", headers=None, auth_token="", authToken="", execution_mode="", sandbox_profile="", auth_required=False, auth_url="", auth_status="", auth_message="": mcp_configure(
            context,
            command=command,
            name=name,
            transport=transport,
            url=url,
            headers=headers,
            auth_token=auth_token or authToken,
            execution_mode=execution_mode,
            sandbox_profile=sandbox_profile,
            auth_required=auth_required,
            auth_url=auth_url,
            auth_status=auth_status,
            auth_message=auth_message,
        ),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.detect_ide",
        "Detect Claude IDE extension MCP lockfiles for the current workspace.",
        IDE_DISCOVERY_SCHEMA,
        lambda cwd="", lockfile_dirs=None, lockfiles=None, include_invalid=False, port=0, skip_valid_check=False, host="": mcp_detect_ide(
            context,
            cwd=cwd,
            lockfile_dirs=lockfile_dirs,
            lockfiles=lockfiles,
            include_invalid=include_invalid,
            port=port,
            skip_valid_check=skip_valid_check,
            host=host,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.configure_ide",
        "Detect and save a Claude IDE extension MCP server for this workspace.",
        MCP_CONFIGURE_IDE_SCHEMA,
        lambda name="ide", cwd="", lockfile_dirs=None, lockfiles=None, include_invalid=False, port=0, skip_valid_check=False, host="", index=-1: mcp_configure_ide(
            context,
            name=name,
            cwd=cwd,
            lockfile_dirs=lockfile_dirs,
            lockfiles=lockfiles,
            include_invalid=include_invalid,
            port=port,
            skip_valid_check=skip_valid_check,
            host=host,
            index=index,
        ),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.ide_extension_status",
        "Check whether the Claude IDE extension is installed for an IDE.",
        IDE_EXTENSION_SCHEMA,
        lambda ide_type="", ideType="", target_version="", targetVersion="": mcp_ide_extension_status(
            context,
            ide_type=ide_type or ideType,
        ),
        metadata={"risk": "low", "requires_process": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.install_ide_extension",
        "Install or update the Claude IDE extension for supported VS Code-family IDEs.",
        IDE_EXTENSION_SCHEMA,
        lambda ide_type="", ideType="", target_version="", targetVersion="": mcp_install_ide_extension(
            context,
            ide_type=ide_type or ideType,
            target_version=target_version or targetVersion,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "requires_process": True,
            "source": "mcp",
            "model_call": True,
        },
    )
    registry.register(
        "mcp.clear",
        "Clear local MCP server configuration and loaded providers for this session.",
        MCP_CLEAR_SCHEMA,
        lambda: mcp_clear(context),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.reload",
        "Reconnect configured MCP servers and swap loaded MCP tool handlers.",
        MCP_RELOAD_SCHEMA,
        lambda: mcp_reload(context, registry),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.reconnect",
        "Reconnect one configured MCP server and swap only that server's tool handlers.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_reconnect(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.enable",
        "Enable a previously configured MCP server for this session scope.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_enable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.disable",
        "Disable a configured MCP server without deleting its saved command.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.remove",
        "Remove a saved MCP server configuration.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_remove(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )


def _register_mcp_prompts(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.prompts",
        "List prompt templates exposed by configured MCP servers.",
        MCP_PROMPTS_SCHEMA,
        lambda server="", query="", max_results=50: mcp_prompts(
            context,
            server=server,
            query=query,
            max_results=max_results,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.get_prompt",
        "Render a prompt template exposed by a configured MCP server.",
        MCP_GET_PROMPT_SCHEMA,
        lambda name, server="", arguments=None: mcp_get_prompt(
            context,
            name=name,
            server=server,
            arguments=arguments,
        ),
        metadata={"risk": "medium", "source": "mcp", "model_call": True},
    )


def _register_mcp_resources(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.resources",
        "List resources exposed by configured MCP servers.",
        MCP_RESOURCES_SCHEMA,
        lambda server="", uri_prefix="", max_results=50: mcp_resources(
            context,
            server=server,
            uri_prefix=uri_prefix,
            max_results=max_results,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.read_resource",
        "Read a resource exposed by a configured MCP server.",
        MCP_READ_RESOURCE_SCHEMA,
        lambda uri, server="": mcp_read_resource(context, uri=uri, server=server),
        metadata={"risk": "medium", "source": "mcp", "model_call": True},
    )

