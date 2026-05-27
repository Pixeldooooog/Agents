import importlib.util
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_TOOL_ROOT = ROOT / "src" / "agents" / "kernel" / "capabilities" / "tools" / "builtin"
SDK_ROOT = ROOT / "src" / "agents" / "sdk"


BUILTIN_REGISTRATION_FILES = {
    "execution_registration.py",
    "extension_registration.py",
    "interaction_registration.py",
    "registration.py",
    "registration_helpers.py",
    "state_registration.py",
    "src_origin_agent_aliases.py",
    "src_origin_discovery_aliases.py",
    "src_origin_plan_aliases.py",
    "src_origin_schedule_aliases.py",
    "src_origin_task_aliases.py",
    "task_schemas.py",
    "tool_names.py",
    "web_registration.py",
    "workspace_registration.py",
    "mcp/registration.py",
}


BUILTIN_IMPLEMENTATION_FILES = {
    "agent_profiles.py",
    "agents.py",
    "browser.py",
    "commands.py",
    "config.py",
    "extensions.py",
    "file_diff.py",
    "file_safety.py",
    "filesystem.py",
    "git.py",
    "hooks.py",
    "image_metadata.py",
    "lsp.py",
    "memory.py",
    "meta.py",
    "notebook.py",
    "patch.py",
    "permissions.py",
    "planning.py",
    "plugins.py",
    "prompts.py",
    "read_errors.py",
    "read_paths.py",
    "schedules.py",
    "search.py",
    "session_context.py",
    "shell.py",
    "shell_lifecycle.py",
    "shell_notifications.py",
    "shell_prompt_stall.py",
    "skill_discovery.py",
    "skill_invocation.py",
    "sleep.py",
    "structured.py",
    "task_src_origin.py",
    "tasks.py",
    "team_memory_safety.py",
    "teams.py",
    "tests.py",
    "user_interaction.py",
    "web.py",
    "workflows.py",
    "worktree.py",
    "mcp/ide.py",
    "mcp/management.py",
    "mcp/prompts.py",
    "mcp/resources.py",
}


SDK_FACADE_OR_WIRING_FILES = {
    "client.py",
    "control_handlers.py",
    "control_payloads.py",
    "event_projection.py",
    "transports.py",
}


SDK_CONTRACT_FILES = {
    "control.py",
    "transport_types.py",
    "types.py",
}


SDK_IMPLEMENTATION_FILES = {
    "async_messages.py",
    "ccr.py",
    "event_artifacts.py",
    "event_auth.py",
    "event_fields.py",
    "event_messages.py",
    "event_payloads.py",
    "event_tasks.py",
    "file_history.py",
    "file_rewind.py",
    "mcp/control.py",
    "options.py",
    "runtime_io.py",
    "session_records.py",
    "structured_io.py",
    "transport_hybrid.py",
    "transport_queue.py",
    "transport_sse.py",
    "transport_websocket.py",
}


def test_agents_namespace_defines_kernel_platform_and_interfaces():
    assert importlib.util.find_spec("agents") is not None
    assert importlib.util.find_spec("agents.kernel") is not None
    assert importlib.util.find_spec("agents.platform") is not None
    assert importlib.util.find_spec("agents.interfaces.server") is not None
    assert importlib.util.find_spec("agents.interfaces.bridge") is not None


def test_agent_system_exposes_future_multi_agent_boundaries():
    kernel_modules = [
        "orchestration",
        "orchestration.types",
        "capabilities.memory",
        "workflows",
        "workflows.types",
        "context",
        "state",
        "state.workspaces",
        "state.workspaces.metadata",
        "governance",
        "governance.credentials",
        "governance.audit",
        "governance.tracing",
        "models",
        "config",
        "specs",
        "state.agents",
        "capabilities",
        "capabilities.memory",
        "capabilities.sandbox",
        "capabilities.skills",
        "capabilities.tools",
        "assembly",
        "state.runs",
        "persistence",
        "state.identity",
        "tasks",
        "mcp",
        "mcp.auth",
        "mcp.config",
        "mcp.loading",
        "mcp.oauth",
        "mcp.oauth_flow",
        "mcp.oauth_runtime",
        "mcp.oauth_tokens",
        "mcp.elicitation_runtime",
        "mcp.list_changed_runtime",
        "mcp.clients",
        "mcp.naming",
        "mcp.provider",
        "mcp.results",
        "mcp.types",
        "mcp.transports.sdk_control",
        "mcp.transports.websocket",
    ]
    for module in kernel_modules:
        assert importlib.util.find_spec(f"agents.kernel.{module}") is not None

    forbidden_kernel_modules = [
        "definitions",
        "integrations",
        "audit",
        "identity",
        "memory",
        "runs",
        "security",
        "skills",
        "storage",
        "tools",
        "tracing",
    ]
    for module in forbidden_kernel_modules:
        assert importlib.util.find_spec(f"agents.kernel.{module}") is None


def test_agent_runtime_is_split_into_explicit_kernel_modules():
    for module in [
        "runtime.loop",
        "context.compiler",
        "runtime.session",
        "context.window",
        "runtime.turns",
        "runtime.turns.model",
        "runtime.turns.tools",
        "governance.permissions",
        "runtime.checkpoints",
        "runtime.state",
        "context.compaction",
        "context.memory",
        "governance.sandbox",
        "governance.security",
    ]:
        assert importlib.util.find_spec(f"agents.kernel.{module}") is not None


def test_agent_capabilities_expose_builtin_tool_boundaries():
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.context") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.local") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.docker") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.execution_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.extension_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.interaction_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.registration_helpers") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.state_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin_agent_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin_discovery_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin_plan_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin_task_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin_schedule_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.management") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.prompts") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.resources") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.ide") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.workspace_registration") is not None


def test_builtin_tool_registration_stays_modular():
    limits = {
        BUILTIN_TOOL_ROOT / "registration.py": 90,
        BUILTIN_TOOL_ROOT / "execution_registration.py": 900,
        BUILTIN_TOOL_ROOT / "extension_registration.py": 320,
        BUILTIN_TOOL_ROOT / "interaction_registration.py": 170,
        BUILTIN_TOOL_ROOT / "state_registration.py": 280,
        BUILTIN_TOOL_ROOT / "src_origin_agent_aliases.py": 900,
        BUILTIN_TOOL_ROOT / "mcp" / "registration.py": 400,
        BUILTIN_TOOL_ROOT / "task_schemas.py": 190,
        BUILTIN_TOOL_ROOT / "web_registration.py": 140,
        BUILTIN_TOOL_ROOT / "workspace_registration.py": 320,
        BUILTIN_TOOL_ROOT / "tool_names.py": 220,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_builtin_tool_registry_wiring_is_separate_from_implementation_modules():
    registration_files = {BUILTIN_TOOL_ROOT / path for path in BUILTIN_REGISTRATION_FILES}

    class_defs = []
    for path in registration_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        class_defs.extend("%s:%s" % (path.relative_to(ROOT), node.name) for node in tree.body if isinstance(node, ast.ClassDef))
    assert not class_defs

    offenders = []
    for path in BUILTIN_TOOL_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "__init__.py" or path in registration_files:
            continue
        names = _top_level_function_names(path)
        register_names = [name for name in names if name.startswith("register_") or name.startswith("_register_")]
        if register_names:
            offenders.append("%s:%s" % (path.relative_to(ROOT), ",".join(register_names)))
    assert not offenders


def test_builtin_tool_files_have_declared_architecture_roles():
    actual = {
        path.relative_to(BUILTIN_TOOL_ROOT).as_posix()
        for path in BUILTIN_TOOL_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    }
    expected = BUILTIN_REGISTRATION_FILES | BUILTIN_IMPLEMENTATION_FILES
    assert actual == expected


def test_builtin_task_domain_stays_split_by_responsibility():
    limits = {
        BUILTIN_TOOL_ROOT / "tasks.py": 520,
        BUILTIN_TOOL_ROOT / "task_src_origin.py": 430,
        BUILTIN_TOOL_ROOT / "task_schemas.py": 190,
        BUILTIN_TOOL_ROOT / "src_origin_task_aliases.py": 900,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_mcp_implementation_is_packaged_by_domain():
    agents_root = ROOT / "src" / "agents"
    kernel_root = ROOT / "src" / "agents" / "kernel"
    tools_root = kernel_root / "capabilities" / "tools"
    builtin_root = tools_root / "builtin"

    assert not list(agents_root.rglob("mcp_*.py"))
    assert not list(kernel_root.glob("mcp_*.py"))
    assert not list(tools_root.glob("mcp_*.py"))
    assert not (tools_root / "mcp.py").exists()
    assert not list(builtin_root.glob("mcp_*.py"))
    assert not (kernel_root / "capabilities" / "mcp_loading.py").exists()


def test_mcp_provider_stays_split_by_responsibility():
    mcp_root = ROOT / "src" / "agents" / "kernel" / "mcp"
    limits = {
        mcp_root / "provider.py": 450,
        mcp_root / "clients.py": 450,
        mcp_root / "types.py": 220,
        mcp_root / "results.py": 180,
        mcp_root / "naming.py": 100,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_sdk_client_stays_split_by_responsibility():
    for module in [
        "async_messages",
        "client",
        "control_handlers",
        "control_payloads",
        "event_artifacts",
        "event_auth",
        "event_fields",
        "event_messages",
        "event_payloads",
        "event_projection",
        "event_tasks",
        "file_history",
        "file_rewind",
        "options",
        "runtime_io",
        "session_records",
    ]:
        assert importlib.util.find_spec(f"agents.sdk.{module}") is not None

    limits = {
        SDK_ROOT / "client.py": 950,
        SDK_ROOT / "async_messages.py": 100,
        SDK_ROOT / "control_handlers.py": 760,
        SDK_ROOT / "control_payloads.py": 420,
        SDK_ROOT / "event_artifacts.py": 120,
        SDK_ROOT / "event_auth.py": 80,
        SDK_ROOT / "event_fields.py": 140,
        SDK_ROOT / "event_messages.py": 620,
        SDK_ROOT / "event_payloads.py": 80,
        SDK_ROOT / "event_projection.py": 120,
        SDK_ROOT / "event_tasks.py": 260,
        SDK_ROOT / "file_history.py": 900,
        SDK_ROOT / "file_rewind.py": 600,
        SDK_ROOT / "options.py": 170,
        SDK_ROOT / "runtime_io.py": 140,
        SDK_ROOT / "session_records.py": 140,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_sdk_files_have_declared_architecture_roles():
    actual = {
        path.relative_to(SDK_ROOT).as_posix()
        for path in SDK_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    }
    expected = SDK_FACADE_OR_WIRING_FILES | SDK_CONTRACT_FILES | SDK_IMPLEMENTATION_FILES
    assert actual == expected


def test_sdk_transports_stay_split_by_protocol():
    for module in ["transports", "transport_types", "transport_queue", "transport_sse", "transport_websocket", "transport_hybrid"]:
        assert importlib.util.find_spec(f"agents.sdk.{module}") is not None

    limits = {
        SDK_ROOT / "transports.py": 120,
        SDK_ROOT / "transport_types.py": 120,
        SDK_ROOT / "transport_queue.py": 80,
        SDK_ROOT / "transport_sse.py": 520,
        SDK_ROOT / "transport_websocket.py": 650,
        SDK_ROOT / "transport_hybrid.py": 420,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_bridge_slash_commands_stay_split_by_domain():
    bridge_root = ROOT / "src" / "agents" / "interfaces" / "bridge"
    for module in [
        "commands",
        "common",
        "extensions",
        "mcp",
        "permissions",
        "prompts",
        "schedules",
        "sessions",
        "tasks",
        "tool_execution",
        "workflows",
    ]:
        assert importlib.util.find_spec(f"agents.interfaces.bridge.slash_commands.{module}") is not None

    limits = {
        bridge_root / "slash.py": 650,
        bridge_root / "slash_commands" / "common.py": 180,
        bridge_root / "slash_commands" / "commands.py": 220,
        bridge_root / "slash_commands" / "extensions.py": 500,
        bridge_root / "slash_commands" / "mcp.py": 260,
        bridge_root / "slash_commands" / "permissions.py": 220,
        bridge_root / "slash_commands" / "prompts.py": 260,
        bridge_root / "slash_commands" / "sessions.py": 380,
        bridge_root / "slash_commands" / "tasks.py": 420,
        bridge_root / "slash_commands" / "schedules.py": 180,
        bridge_root / "slash_commands" / "tool_execution.py": 160,
        bridge_root / "slash_commands" / "workflows.py": 300,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_agent_models_split_protocol_adapters_and_transports():
    assert importlib.util.find_spec("agents.kernel.models.adapters") is not None
    assert importlib.util.find_spec("agents.kernel.models.protocol") is not None
    assert importlib.util.find_spec("agents.kernel.models.transports") is not None


def test_platform_and_server_expose_control_and_protocol_boundaries():
    assert importlib.util.find_spec("agents.platform.persistence") is not None
    assert importlib.util.find_spec("agents.platform.sessions") is not None
    assert importlib.util.find_spec("agents.platform.commands") is not None
    assert importlib.util.find_spec("agents.platform.profiles") is not None
    assert importlib.util.find_spec("agents.interfaces.server.auth") is not None
    assert importlib.util.find_spec("agents.interfaces.server.streaming") is not None
    assert importlib.util.find_spec("agents.interfaces.bridge.ndjson") is not None


def test_legacy_app_package_is_not_importable():
    assert importlib.util.find_spec("app") is None


def test_bridge_does_not_import_server():
    imports = _imports_under(ROOT / "src" / "agents" / "interfaces" / "bridge")

    assert not [name for name in imports if name == "agents.interfaces.server" or name.startswith("agents.interfaces.server.")]


def test_platform_does_not_import_interface_adapters():
    imports = _imports_under(ROOT / "src" / "agents" / "platform")
    forbidden = ("agents.interfaces.server", "agents.interfaces.bridge")

    assert not [name for name in imports if name in forbidden or name.startswith(tuple("%s." % item for item in forbidden))]


def test_agent_does_not_import_entrypoint_or_ui_packages():
    imports = _imports_under(ROOT / "src" / "agents" / "kernel")
    forbidden = (
        "agents.interfaces.server",
        "agents.interfaces.bridge",
        "agents.entrypoints",
        "fastapi",
        "typer",
        "rich",
        "prompt_toolkit",
    )

    assert not [name for name in imports if name in forbidden or name.startswith(tuple("%s." % item for item in forbidden))]


def test_legacy_top_level_packages_are_not_importable():
    assert importlib.util.find_spec("agent") is None
    assert importlib.util.find_spec("server") is None
    assert importlib.util.find_spec("bridge") is None
    assert importlib.util.find_spec("entrypoints") is None
    assert importlib.util.find_spec("gateway") is None
    assert importlib.util.find_spec("cli") is None


def test_server_template_engine_and_provider_layers_are_not_importable():
    assert importlib.util.find_spec("agents.interfaces.server.engines") is None
    assert importlib.util.find_spec("agents.interfaces.server.shared") is None


def _imports_under(root: Path) -> set[str]:
    imports: set[str] = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def _top_level_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
