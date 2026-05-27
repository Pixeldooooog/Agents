import importlib.util
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_TOOL_ROOT = ROOT / "src" / "agents" / "kernel" / "capabilities" / "tools" / "builtin"
SDK_ROOT = ROOT / "src" / "agents" / "sdk"


BUILTIN_REGISTRATION_FILES = {
    "execution_registration.py",
    "automation_registration.py",
    "collaboration_registration.py",
    "development_registration.py",
    "extension_registration.py",
    "interaction_registration.py",
    "registration.py",
    "registration_helpers.py",
    "runtime_registration.py",
    "state_registration.py",
    "src_origin/aliases.py",
    "src_origin/agent_aliases.py",
    "src_origin/core_aliases.py",
    "src_origin/discovery_aliases.py",
    "src_origin/plan_aliases.py",
    "src_origin/schedule_aliases.py",
    "src_origin/session_aliases.py",
    "src_origin/task_aliases.py",
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
    "filesystem_limits.py",
    "filesystem_media.py",
    "filesystem_memory.py",
    "filesystem_read.py",
    "filesystem_results.py",
    "git.py",
    "hooks.py",
    "image_metadata.py",
    "lsp.py",
    "memory.py",
    "meta.py",
    "notebook.py",
    "patch.py",
    "patch_payload.py",
    "patch_planner.py",
    "patch_text.py",
    "patch_types.py",
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
    "worktree_git.py",
    "worktree_naming.py",
    "worktree_setup.py",
    "worktree_state.py",
    "mcp/ide.py",
    "mcp/management.py",
    "mcp/prompts.py",
    "mcp/resources.py",
    "mcp/runtime.py",
    "mcp/settings.py",
    "mcp/store.py",
}


SDK_FACADE_OR_WIRING_FILES = {
    "client.py",
    "control_handlers.py",
    "control_payloads.py",
    "event_projection.py",
    "sessions.py",
    "transports.py",
}


SDK_CONTRACT_FILES = {
    "control.py",
    "ccr_types.py",
    "transport_types.py",
    "types.py",
}


SDK_IMPLEMENTATION_FILES = {
    "async_messages.py",
    "ccr_auth.py",
    "ccr.py",
    "ccr_stream.py",
    "ccr_worker_state.py",
    "control_async_state.py",
    "control_files.py",
    "control_interactions.py",
    "control_system.py",
    "control_tasks.py",
    "event_artifacts.py",
    "event_auth.py",
    "event_fields.py",
    "event_messages.py",
    "event_payloads.py",
    "event_tasks.py",
    "file_history.py",
    "file_history_migration.py",
    "file_history_paths.py",
    "file_history_recorder.py",
    "file_history_rewind.py",
    "file_history_snapshots.py",
    "file_history_types.py",
    "file_rewind.py",
    "mcp/control.py",
    "mcp/control_responses.py",
    "options.py",
    "runtime_io.py",
    "session_compaction.py",
    "session_records.py",
    "session_stream.py",
    "structured_io.py",
    "stdin_runner.py",
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
        "governance.tool_impact",
        "governance.tool_impact_arguments",
        "governance.tool_impact_common",
        "governance.tool_impact_domains",
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
        "assembly.active_tools",
        "assembly.common",
        "assembly.plugins",
        "assembly.session_state",
        "assembly.spec_overrides",
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
        "runtime.tool_stream",
        "context.window",
        "runtime.turns",
        "runtime.turns.model",
        "runtime.turns.tool_summary",
        "runtime.turns.tools",
        "runtime.recovery",
        "governance.permissions",
        "runtime.checkpoints",
        "runtime.state",
        "runtime.session_compaction",
        "runtime.session_lifecycle",
        "runtime.session_messages",
        "context.compaction",
        "context.compaction_metadata",
        "context.compaction_model",
        "context.compaction_prompts",
        "context.memory",
        "governance.sandbox",
        "governance.security",
    ]:
        assert importlib.util.find_spec(f"agents.kernel.{module}") is not None


def test_agent_runtime_modules_stay_split_by_responsibility():
    runtime_root = ROOT / "src" / "agents" / "kernel" / "runtime"
    limits = {
        runtime_root / "loop.py": 460,
        runtime_root / "recovery.py": 90,
        runtime_root / "session.py": 230,
        runtime_root / "tool_stream.py": 80,
        runtime_root / "turns" / "model.py": 90,
        runtime_root / "turns" / "tools.py": 320,
        runtime_root / "turns" / "tool_summary.py": 240,
        runtime_root / "checkpoints.py": 190,
        runtime_root / "session_compaction.py": 60,
        runtime_root / "session_lifecycle.py": 80,
        runtime_root / "session_messages.py": 30,
        runtime_root / "state.py": 40,
    }
    context_root = ROOT / "src" / "agents" / "kernel" / "context"
    limits[context_root / "compaction_metadata.py"] = 90
    limits[context_root / "compaction_model.py"] = 120
    limits[context_root / "compaction_prompts.py"] = 120

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_governance_tool_impact_stays_split_by_responsibility():
    governance_root = ROOT / "src" / "agents" / "kernel" / "governance"
    limits = {
        governance_root / "tool_impact.py": 420,
        governance_root / "tool_impact_arguments.py": 160,
        governance_root / "tool_impact_common.py": 220,
        governance_root / "tool_impact_domains.py": 360,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_governance_tool_rules_stay_split_by_responsibility():
    governance_root = ROOT / "src" / "agents" / "kernel" / "governance"
    for module in [
        "tool_rules",
        "tool_rule_names",
        "tool_rule_parser",
        "tool_rule_patterns",
        "tool_rule_shell",
        "tool_rule_targets",
        "tool_rule_types",
    ]:
        assert importlib.util.find_spec(f"agents.kernel.governance.{module}") is not None

    limits = {
        governance_root / "tool_rules.py": 180,
        governance_root / "tool_rule_names.py": 120,
        governance_root / "tool_rule_parser.py": 110,
        governance_root / "tool_rule_patterns.py": 90,
        governance_root / "tool_rule_shell.py": 230,
        governance_root / "tool_rule_targets.py": 150,
        governance_root / "tool_rule_types.py": 40,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_session_assembly_stays_split_by_responsibility():
    assembly_root = ROOT / "src" / "agents" / "kernel" / "assembly"
    limits = {
        assembly_root / "session.py": 360,
        assembly_root / "active_tools.py": 120,
        assembly_root / "common.py": 60,
        assembly_root / "plugins.py": 160,
        assembly_root / "session_state.py": 220,
        assembly_root / "spec_overrides.py": 100,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_agent_capabilities_expose_builtin_tool_boundaries():
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.contracts") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.context") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.registry") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.results") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.validation") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.local") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.local_files") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.local_process") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.local_search") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.docker") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.sandbox.docker_search_scripts") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.automation_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.collaboration_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.development_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.execution_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.extension_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.interaction_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.patch_payload") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.patch_planner") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.patch_text") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.patch_types") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.registration_helpers") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.runtime_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.state_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.agent_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.core_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.discovery_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.plan_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.session_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.task_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.src_origin.schedule_aliases") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.management") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.prompts") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.resources") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.ide") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.runtime") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.settings") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.mcp.store") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.workspace_registration") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.worktree_git") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.worktree_naming") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.worktree_setup") is not None
    assert importlib.util.find_spec("agents.kernel.capabilities.tools.builtin.worktree_state") is not None


def test_builtin_tool_registration_stays_modular():
    limits = {
        BUILTIN_TOOL_ROOT / "automation_registration.py": 310,
        BUILTIN_TOOL_ROOT / "collaboration_registration.py": 170,
        BUILTIN_TOOL_ROOT / "development_registration.py": 260,
        BUILTIN_TOOL_ROOT / "registration.py": 90,
        BUILTIN_TOOL_ROOT / "execution_registration.py": 80,
        BUILTIN_TOOL_ROOT / "extension_registration.py": 320,
        BUILTIN_TOOL_ROOT / "interaction_registration.py": 170,
        BUILTIN_TOOL_ROOT / "runtime_registration.py": 170,
        BUILTIN_TOOL_ROOT / "state_registration.py": 280,
        BUILTIN_TOOL_ROOT / "src_origin" / "aliases.py": 80,
        BUILTIN_TOOL_ROOT / "src_origin" / "agent_aliases.py": 300,
        BUILTIN_TOOL_ROOT / "src_origin" / "core_aliases.py": 330,
        BUILTIN_TOOL_ROOT / "src_origin" / "session_aliases.py": 220,
        BUILTIN_TOOL_ROOT / "mcp" / "registration.py": 400,
        BUILTIN_TOOL_ROOT / "task_schemas.py": 190,
        BUILTIN_TOOL_ROOT / "web_registration.py": 140,
        BUILTIN_TOOL_ROOT / "workspace_registration.py": 320,
        BUILTIN_TOOL_ROOT / "tool_names.py": 220,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_tool_registry_stays_split_by_responsibility():
    tools_root = ROOT / "src" / "agents" / "kernel" / "capabilities" / "tools"
    limits = {
        tools_root / "contracts.py": 180,
        tools_root / "registry.py": 480,
        tools_root / "results.py": 120,
        tools_root / "validation.py": 120,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_sandbox_provider_modules_stay_split_by_responsibility():
    sandbox_root = ROOT / "src" / "agents" / "kernel" / "capabilities" / "sandbox"
    limits = {
        sandbox_root / "local.py": 380,
        sandbox_root / "local_files.py": 90,
        sandbox_root / "local_process.py": 120,
        sandbox_root / "local_search.py": 320,
        sandbox_root / "docker.py": 700,
        sandbox_root / "docker_search_scripts.py": 340,
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


def test_builtin_package_entrypoint_stays_thin():
    package_init = BUILTIN_TOOL_ROOT / "__init__.py"
    assert len(package_init.read_text(encoding="utf-8").splitlines()) <= 40


def test_builtin_task_domain_stays_split_by_responsibility():
    limits = {
        BUILTIN_TOOL_ROOT / "tasks.py": 520,
        BUILTIN_TOOL_ROOT / "task_src_origin.py": 430,
        BUILTIN_TOOL_ROOT / "task_schemas.py": 190,
        BUILTIN_TOOL_ROOT / "src_origin" / "task_aliases.py": 900,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_builtin_patch_domain_stays_split_by_responsibility():
    limits = {
        BUILTIN_TOOL_ROOT / "patch.py": 260,
        BUILTIN_TOOL_ROOT / "patch_payload.py": 150,
        BUILTIN_TOOL_ROOT / "patch_planner.py": 240,
        BUILTIN_TOOL_ROOT / "patch_text.py": 180,
        BUILTIN_TOOL_ROOT / "patch_types.py": 60,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_builtin_worktree_domain_stays_split_by_responsibility():
    limits = {
        BUILTIN_TOOL_ROOT / "worktree.py": 260,
        BUILTIN_TOOL_ROOT / "worktree_git.py": 140,
        BUILTIN_TOOL_ROOT / "worktree_naming.py": 120,
        BUILTIN_TOOL_ROOT / "worktree_setup.py": 260,
        BUILTIN_TOOL_ROOT / "worktree_state.py": 150,
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


def test_builtin_mcp_management_stays_split_by_responsibility():
    mcp_builtin_root = BUILTIN_TOOL_ROOT / "mcp"
    limits = {
        mcp_builtin_root / "management.py": 320,
        mcp_builtin_root / "runtime.py": 220,
        mcp_builtin_root / "settings.py": 180,
        mcp_builtin_root / "store.py": 140,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_builtin_filesystem_stays_split_by_responsibility():
    for module in [
        "filesystem",
        "filesystem_limits",
        "filesystem_media",
        "filesystem_memory",
        "filesystem_read",
        "filesystem_results",
    ]:
        assert importlib.util.find_spec(f"agents.kernel.capabilities.tools.builtin.{module}") is not None

    limits = {
        BUILTIN_TOOL_ROOT / "filesystem.py": 140,
        BUILTIN_TOOL_ROOT / "filesystem_limits.py": 90,
        BUILTIN_TOOL_ROOT / "filesystem_media.py": 300,
        BUILTIN_TOOL_ROOT / "filesystem_memory.py": 110,
        BUILTIN_TOOL_ROOT / "filesystem_read.py": 170,
        BUILTIN_TOOL_ROOT / "filesystem_results.py": 120,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_sdk_client_stays_split_by_responsibility():
    for module in [
        "async_messages",
        "client",
        "control_async_state",
        "control_files",
        "control_handlers",
        "control_interactions",
        "control_payloads",
        "control_system",
        "control_tasks",
        "event_artifacts",
        "event_auth",
        "event_fields",
        "event_messages",
        "event_payloads",
        "event_projection",
        "event_tasks",
        "file_history",
        "file_history_migration",
        "file_history_paths",
        "file_history_recorder",
        "file_history_rewind",
        "file_history_snapshots",
        "file_history_types",
        "file_rewind",
        "mcp.control",
        "mcp.control_responses",
        "options",
        "runtime_io",
        "session_compaction",
        "session_records",
        "session_stream",
        "sessions",
        "stdin_runner",
    ]:
        assert importlib.util.find_spec(f"agents.sdk.{module}") is not None

    limits = {
        SDK_ROOT / "client.py": 700,
        SDK_ROOT / "async_messages.py": 100,
        SDK_ROOT / "control_async_state.py": 150,
        SDK_ROOT / "control_files.py": 170,
        SDK_ROOT / "control_handlers.py": 160,
        SDK_ROOT / "control_interactions.py": 70,
        SDK_ROOT / "control_payloads.py": 420,
        SDK_ROOT / "control_system.py": 90,
        SDK_ROOT / "control_tasks.py": 70,
        SDK_ROOT / "event_artifacts.py": 120,
        SDK_ROOT / "event_auth.py": 80,
        SDK_ROOT / "event_fields.py": 140,
        SDK_ROOT / "event_messages.py": 620,
        SDK_ROOT / "event_payloads.py": 80,
        SDK_ROOT / "event_projection.py": 120,
        SDK_ROOT / "event_tasks.py": 260,
        SDK_ROOT / "file_history.py": 80,
        SDK_ROOT / "file_history_migration.py": 150,
        SDK_ROOT / "file_history_paths.py": 140,
        SDK_ROOT / "file_history_recorder.py": 240,
        SDK_ROOT / "file_history_rewind.py": 150,
        SDK_ROOT / "file_history_snapshots.py": 210,
        SDK_ROOT / "file_history_types.py": 60,
        SDK_ROOT / "file_rewind.py": 600,
        SDK_ROOT / "mcp" / "control.py": 120,
        SDK_ROOT / "mcp" / "control_responses.py": 220,
        SDK_ROOT / "options.py": 170,
        SDK_ROOT / "runtime_io.py": 140,
        SDK_ROOT / "session_compaction.py": 120,
        SDK_ROOT / "session_records.py": 140,
        SDK_ROOT / "session_stream.py": 60,
        SDK_ROOT / "sessions.py": 140,
        SDK_ROOT / "stdin_runner.py": 170,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


def test_sdk_mcp_control_implementation_lives_in_mcp_package():
    assert not (SDK_ROOT / "control_mcp.py").exists()
    assert importlib.util.find_spec("agents.sdk.mcp.control") is not None
    assert importlib.util.find_spec("agents.sdk.mcp.control_responses") is not None


def test_sdk_files_have_declared_architecture_roles():
    actual = {
        path.relative_to(SDK_ROOT).as_posix()
        for path in SDK_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    }
    expected = SDK_FACADE_OR_WIRING_FILES | SDK_CONTRACT_FILES | SDK_IMPLEMENTATION_FILES
    assert actual == expected


def test_sdk_ccr_stays_split_by_responsibility():
    for module in ["ccr", "ccr_types", "ccr_auth", "ccr_stream", "ccr_worker_state"]:
        assert importlib.util.find_spec(f"agents.sdk.{module}") is not None

    limits = {
        SDK_ROOT / "ccr.py": 560,
        SDK_ROOT / "ccr_types.py": 120,
        SDK_ROOT / "ccr_auth.py": 80,
        SDK_ROOT / "ccr_stream.py": 140,
        SDK_ROOT / "ccr_worker_state.py": 130,
    }

    for path, max_lines in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= max_lines, path


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


def test_bridge_payloads_stay_split_by_domain():
    bridge_root = ROOT / "src" / "agents" / "interfaces" / "bridge"
    for module in ["payloads", "payload_format", "payload_tools"]:
        assert importlib.util.find_spec(f"agents.interfaces.bridge.{module}") is not None

    limits = {
        bridge_root / "payloads.py": 560,
        bridge_root / "payload_format.py": 150,
        bridge_root / "payload_tools.py": 150,
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
