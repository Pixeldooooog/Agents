import importlib.util
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
