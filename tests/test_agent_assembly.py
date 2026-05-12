# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：test_agent_assembly.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

import asyncio
import json

from agents.kernel.assembly import create_agent_session, create_agent_session_async
from agents.kernel.capabilities.memory import InMemoryMemoryStore, MemoryRecord, MemoryScope
from agents.kernel.config import AgentConfigError, resolve_model_client_config
from agents.kernel.mcp_config import InMemoryMCPConfigStore, MCPServerRecord
from agents.kernel.session_state import InMemorySessionStateStore, SessionStateRecord
from agents.kernel.specs import AgentSpec


class FakeModelConfig:
    API_KEY = ""
    BASE_URL = ""
    MODEL = ""


class FakeModelsConfig:
    def __init__(self):
        self.openai = FakeModelConfig()
        self.openai_responses = FakeModelConfig()
        self.anthropic = FakeModelConfig()
        self.gemini = FakeModelConfig()


class FakeAgentConfig:
    PROTOCOL = "openai-chat"
    TIMEOUT = 60.0
    MAX_TOKENS = 4096
    MAX_TOOL_ITERATIONS = 8
    SYSTEM_PROMPT = ""
    ENABLED_TOOLS = ""
    SKILLS = ""
    WORKSPACE_ROOT = ".agents/workspaces"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0
    MAX_CONTEXT_TOKENS = 256000
    MAX_CONCURRENT_TOOLS = 10
    MAX_CONCURRENT_REQUESTS = 20
    TOOL_TIMEOUT = 60.0
    GUIDED_TOOLS = ""
    BUILTIN_TOOLS = ""
    SANDBOX_ALLOW_FILE_WRITE = False
    SANDBOX_ALLOW_PROCESS = False
    SANDBOX_ALLOW_NETWORK = False
    SANDBOX_ALLOWED_COMMANDS = ""
    MEMORY_CONTEXT_LIMIT = 20
    HTTP_PROXY = ""
    HTTPS_PROXY = ""
    ALL_PROXY = ""
    CLAUDE_API_KEY = ""
    CLAUDE_BASE_URL = ""
    CLAUDE_MODEL = ""


class FakeSettings:
    def __init__(self):
        self.agent = FakeAgentConfig()
        self.models = FakeModelsConfig()
        self.server = FakeServerConfig()
        self.mcp = FakeMcpConfig()


class FakeServerConfig:
    ROOT_PATH = "."


class FakeMcpConfig:
    SERVER_COMMAND = ""
    SERVER_NAME = ""
    CLIENT_TIMEOUT = 5.0
    EXECUTION_MODE = ""
    SANDBOX_PROFILE = ""


class FakeRuntimeClient:
    async def async_complete(self, request_data):
        raise RuntimeError("not used")

    async def async_stream(self, request_data):
        raise RuntimeError("not used")


def test_claude_config_prefers_agent_specific_values():
    settings = FakeSettings()
    settings.agent.CLAUDE_API_KEY = "project-key"
    settings.agent.CLAUDE_BASE_URL = "https://project.example/v1"
    settings.agent.CLAUDE_MODEL = "project-claude"
    settings.models.anthropic.API_KEY = "global-key"
    settings.models.anthropic.BASE_URL = "https://global.example/v1"
    settings.models.anthropic.MODEL = "global-claude"

    config = resolve_model_client_config(settings, protocol="claude-messages")

    assert config.api_key == "project-key"
    assert config.base_url == "https://project.example/v1"
    assert config.model == "project-claude"


def test_claude_config_falls_back_to_anthropic_when_agent_specific_values_are_empty():
    settings = FakeSettings()
    settings.models.anthropic.API_KEY = "global-key"
    settings.models.anthropic.BASE_URL = "https://global.example/v1"
    settings.models.anthropic.MODEL = "global-claude"

    config = resolve_model_client_config(settings, protocol="claude-messages")

    assert config.api_key == "global-key"
    assert config.base_url == "https://global.example/v1"
    assert config.model == "global-claude"


def test_partial_agent_claude_config_falls_back_to_global_anthropic_values():
    settings = FakeSettings()
    settings.agent.CLAUDE_BASE_URL = "https://project.example/v1"
    settings.agent.CLAUDE_MODEL = "project-claude"
    settings.models.anthropic.API_KEY = "global-key"

    config = resolve_model_client_config(settings, protocol="claude-messages")

    assert config.api_key == "global-key"
    assert config.base_url == "https://project.example/v1"
    assert config.model == "project-claude"


def test_model_config_uses_project_proxy_settings():
    settings = FakeSettings()
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    settings.agent.HTTP_PROXY = "http://127.0.0.1:7890"
    settings.agent.HTTPS_PROXY = "http://127.0.0.1:7890"
    settings.agent.ALL_PROXY = "socks5://127.0.0.1:7890"

    config = resolve_model_client_config(settings, protocol="openai-chat")

    assert config.proxy_url == "http://127.0.0.1:7890"


def test_create_session_composes_skill_prompt_and_declared_tools(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus on agents.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "prompt_fragments": ["prompts/focus.md"],
                "tools": ["filesystem.read"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.SYSTEM_PROMPT = "Base prompt."
    settings.agent.SKILLS = "focus"
    settings.agent.ENABLED_TOOLS = "filesystem.list"
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = create_agent_session(settings, AgentSpec())

    assert "## system: system.user_configured\nBase prompt." in session.system_prompt
    assert "## skills: skill.focus.0\nFocus on agents." in session.system_prompt
    assert "## runtime_policy: runtime.tool_contract" in session.system_prompt
    assert session.runtime.enabled_tools == ["filesystem.list", "filesystem.read"]
    assert session.workspace.tenant_id == "default"
    assert session.workspace.user_id == "anonymous"
    assert session.workspace.agent_id == "default"
    assert session.workspace.workspace_id == "default"
    assert session.workspace.path == tmp_path / ".agents" / "workspaces" / "local" / "default"
    assert any(item.id == "skill.focus.0" and item.included for item in session.context_trace)
    assert session.tool_context.enabled_tools == session.runtime.enabled_tools
    assert session.tool_context.skill_registry.names() == ["focus"]


def test_create_session_respects_explicit_enabled_tools(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps({"name": "focus", "tools": ["filesystem.list"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.SKILLS = "focus"
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = create_agent_session(settings, AgentSpec.from_overrides(enabled_tools=["filesystem.read"]))

    assert session.runtime.enabled_tools == ["filesystem.read"]


def test_create_session_rejects_unknown_enabled_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.ENABLED_TOOLS = "missing.tool"
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    try:
        create_agent_session(settings, AgentSpec())
    except AgentConfigError as exc:
        assert "unknown enabled tool(s): missing.tool" in str(exc)
    else:
        raise AssertionError("expected unknown tool configuration to fail")


def test_create_session_uses_configured_builtin_tools_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.BUILTIN_TOOLS = "filesystem.read,filesystem.list"
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = create_agent_session(settings, AgentSpec())

    assert session.runtime.enabled_tools == ["filesystem.read", "filesystem.list"]


def test_create_session_can_enable_web_search_tool(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.BUILTIN_TOOLS = "web.search"
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = create_agent_session(settings, AgentSpec())

    assert session.runtime.enabled_tools == ["web.search"]
    assert session.runtime.tools.specs(["web.search"])[0].raw["metadata"]["provider"] == "none"


def test_create_session_injects_memory_context(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.agent.SYSTEM_PROMPT = "Configured prompt."
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    store = InMemoryMemoryStore()

    async def create():
        await store.save(
            MemoryRecord.create(
                tenant_id="default",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="default",
                scope=MemoryScope.WORKSPACE,
                content="User wants concise implementation notes.",
            )
        )
        return await create_agent_session_async(
            settings,
            AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"),
            memory_store=store,
        )

    session = asyncio.run(create())

    assert "## memory: memory." in session.system_prompt
    assert "User wants concise implementation notes." in session.system_prompt
    assert session.tool_context.memory_store is store


def test_create_session_hydrates_mcp_config_store_before_loading(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    captured = {}

    async def fake_load_mcp(settings, registry):
        captured["name"] = settings.mcp.SERVER_NAME
        captured["command"] = settings.mcp.SERVER_COMMAND
        captured["execution_mode"] = settings.mcp.EXECUTION_MODE
        captured["sandbox_profile"] = settings.mcp.SANDBOX_PROFILE
        return []

    monkeypatch.setattr("agents.kernel.assembly.session.load_configured_mcp", fake_load_mcp)
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    store = InMemoryMCPConfigStore()

    async def create():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python server.py",
                execution_mode="workspace",
                sandbox_profile="coding",
                tenant_id="default",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="default",
            )
        )
        return await create_agent_session_async(
            settings,
            AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"),
            mcp_config_store=store,
        )

    session = asyncio.run(create())

    assert captured == {
        "name": "docs",
        "command": "python server.py",
        "execution_mode": "workspace",
        "sandbox_profile": "coding",
    }
    assert session.tool_context.mcp_config_store is store


def test_create_session_hydrates_session_state_store(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Persisted skill prompt.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "prompt_fragments": ["prompts/focus.md"],
                "tools": ["filesystem.read"],
            }
        ),
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "planner",
                "prompt": "Persisted plugin prompt.",
                "tools": ["todo.write"],
            }
        ),
        encoding="utf-8",
    )
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    store = InMemorySessionStateStore()

    async def create():
        await store.save(
            SessionStateRecord(
                tenant_id="default",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="default",
                todos=[
                    {"content": "Run checks", "status": "in_progress", "activeForm": "Running checks"},
                ],
                plan_mode=True,
                plan_text="Inspect then implement.",
                plan_allowed_prompts=[{"tool": "shell.run", "prompt": "pytest"}],
                system_prompt_override="Persisted session prompt.",
                system_prompt_overridden=True,
                permission_profile_override="guarded",
                permission_mode_override="auto",
                permission_restrict_allowed_tools=True,
                permission_allowed_tools_override=["filesystem.read"],
                permission_denied_tools_override=["shell.run"],
                approval_required_tools_override=["shell.run"],
                permission_overridden=True,
                enabled_skills=["focus"],
                enabled_plugins=["planner"],
                skill_tools={"focus": ["filesystem.read"]},
                plugin_tools={"planner": ["todo.write"]},
            )
        )
        return await create_agent_session_async(
            settings,
            AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"),
            session_state_store=store,
        )

    session = asyncio.run(create())

    assert session.tool_context.session_state_store is store
    assert session.tool_context.todos[0]["content"] == "Run checks"
    assert session.tool_context.plan_mode is True
    assert session.tool_context.plan_text == "Inspect then implement."
    assert session.tool_context.plan_allowed_prompts == [{"tool": "shell.run", "prompt": "pytest"}]
    assert session.tool_context.system_prompt_override == "Persisted session prompt."
    assert session.tool_context.system_prompt_overridden is True
    assert "Persisted session prompt." in session.system_prompt
    assert "Persisted skill prompt." in session.system_prompt
    assert "Persisted plugin prompt." in session.system_prompt
    assert "Configured prompt." not in session.system_prompt
    assert session.tool_context.permission_profile_override == "guarded"
    assert session.tool_context.permission_mode_override == "auto"
    assert session.tool_context.permission_restrict_allowed_tools is True
    assert session.tool_context.permission_allowed_tools_override == ["filesystem.read"]
    assert session.tool_context.permission_denied_tools_override == ["shell.run"]
    assert session.tool_context.approval_required_tools_override == ["shell.run"]
    assert session.tool_context.permission_overridden is True
    assert session.tool_context.agent_spec.permission_profile == "guarded"
    assert session.tool_context.agent_spec.tool_permissions.mode == "auto"
    assert session.tool_context.agent_spec.tool_permissions.allowed_tools == ["filesystem.read"]
    assert session.tool_context.agent_spec.tool_permissions.denied_tools == ["shell.run"]
    assert session.tool_context.agent_spec.tool_permissions.approval_required_tools == ["shell.run"]
    assert session.tool_context.enabled_skills == {"focus"}
    assert session.tool_context.enabled_plugins == {"planner"}
    assert session.tool_context.skill_tools == {"focus": ["filesystem.read"]}
    assert session.tool_context.plugin_tools == {"planner": ["todo.write"]}
    assert "filesystem.read" in session.runtime.enabled_tools
    assert "todo.write" in session.runtime.enabled_tools


def test_create_session_uses_agent_spec(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps({"name": "focus", "tools": ["filesystem.read"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "settings-model"
    spec = AgentSpec.from_overrides(
        protocol="openai-chat",
        model="spec-model",
        agent_id="agent 1",
        user_id="user 1",
        skills=["focus"],
    )

    session = create_agent_session(settings, spec)

    assert session.runtime.model == "spec-model"
    assert session.runtime.enabled_tools == ["filesystem.read"]
    assert session.workspace.user_id == "user-1"
    assert session.workspace.agent_id == "agent-1"


def test_create_session_loads_workspace_agents_md(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    workspace = tmp_path / ".agents" / "workspaces" / "default" / "user-1" / "agent-1" / "default"
    workspace.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("Workspace instruction.", encoding="utf-8")

    session = create_agent_session(settings, AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"))

    assert session.workspace.tenant_id == "default"
    assert session.workspace.user_id == "user-1"
    assert session.workspace.agent_id == "agent-1"
    assert session.workspace.workspace_id == "default"
    assert "## project_instructions: workspace.agents\nWorkspace instruction." in session.system_prompt


def test_create_session_can_use_explicit_workspace_path(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Local coding workspace.", encoding="utf-8")

    session = create_agent_session(
        settings,
        AgentSpec.from_overrides(
            user_id="user 1",
            agent_id="agent 1",
            workspace_path=str(workspace),
        ),
    )

    assert session.workspace.path == workspace
    assert session.workspace.workspace_id == "project"
    assert "Local coding workspace." in session.system_prompt


def test_async_create_session_can_run_inside_event_loop(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    async def create():
        return await create_agent_session_async(settings, AgentSpec())

    session = asyncio.run(create())

    assert session.runtime.protocol == "openai-chat"
    assert session.workspace.path.exists()
