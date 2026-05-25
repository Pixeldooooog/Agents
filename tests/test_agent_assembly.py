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
from agents.kernel.capabilities.tools.mcp import MCPServerConfig, MCPToolProvider
from agents.kernel.config import AgentConfigError, resolve_model_client_config
from agents.kernel.mcp_auth import InMemoryMCPAuthTokenStore, MCPAuthTokenRecord
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


class FakeCloseableMCPClient:
    def __init__(self):
        self.closed = False

    async def list_tools(self):
        return []

    async def call_tool(self, name, arguments):
        raise RuntimeError("not used")

    async def list_resources(self):
        return []

    async def read_resource(self, uri):
        raise RuntimeError("not used")

    async def list_prompts(self):
        return []

    async def get_prompt(self, name, arguments=None):
        raise RuntimeError("not used")

    async def close(self):
        self.closed = True


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


def test_create_session_filters_blanket_denied_tools_before_model_context(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    spec = AgentSpec.from_overrides(
        enabled_tools=["Read", "filesystem.read", "Bash", "NotebookEdit"],
        denied_tools=["Read", "Bash(git *)", "NotebookEdit(secrets/**)"],
    )

    session = create_agent_session(settings, spec)

    assert session.runtime.enabled_tools == ["Bash", "NotebookEdit"]
    assert session.tool_context.enabled_tools == ["Bash", "NotebookEdit"]


def test_create_session_accepts_src_origin_tool_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = create_agent_session(
        settings,
        AgentSpec.from_overrides(
            enabled_tools=[
                "Read",
                "Edit",
                "Bash",
                "WebSearch",
                "WebFetch",
                "ListMcpResourcesTool",
                "TaskOutput",
                "TaskStop",
                "TaskCreate",
                "TaskUpdate",
                "CronCreate",
                "ToolSearch",
                "EnterPlanMode",
                "ExitPlanMode",
                "Agent",
                "Task",
                "SendMessage",
                "TeamCreate",
                "TeamDelete",
                "StructuredOutput",
                "Skill",
                "LSP",
                "Config",
                "AskUserQuestion",
                "SendUserMessage",
                "Brief",
                "EnterWorktree",
                "ExitWorktree",
            ]
        ),
    )

    assert session.runtime.enabled_tools == [
        "Read",
        "Edit",
        "Bash",
        "WebSearch",
        "WebFetch",
        "ListMcpResourcesTool",
        "TaskOutput",
        "TaskStop",
        "TaskCreate",
        "TaskUpdate",
        "CronCreate",
        "ToolSearch",
        "EnterPlanMode",
        "ExitPlanMode",
        "Agent",
        "Task",
        "SendMessage",
        "TeamCreate",
        "TeamDelete",
        "StructuredOutput",
        "Skill",
        "LSP",
        "Config",
        "AskUserQuestion",
        "SendUserMessage",
        "Brief",
        "EnterWorktree",
        "ExitWorktree",
    ]
    specs = {spec.name: spec for spec in session.runtime.tools.specs(session.runtime.enabled_tools)}
    assert specs["Read"].raw["metadata"]["alias_of"] == "filesystem.read"
    assert specs["Edit"].raw["metadata"]["alias_of"] == "patch.apply"
    assert specs["Bash"].raw["metadata"]["alias_of"] == "shell.run"
    assert specs["WebSearch"].raw["metadata"]["alias_of"] == "web.search"
    assert specs["WebFetch"].raw["metadata"]["alias_of"] == "web.extract"
    assert specs["ListMcpResourcesTool"].raw["metadata"]["alias_of"] == "mcp.resources"
    assert specs["TaskOutput"].raw["metadata"]["alias_of"] == "task.output"
    assert specs["TaskStop"].raw["metadata"]["alias_of"] == "task.stop"
    assert specs["TaskCreate"].raw["metadata"]["alias_of"] == "task.create"
    assert specs["TaskUpdate"].raw["metadata"]["alias_of"] == "task.update"
    assert specs["CronCreate"].raw["metadata"]["alias_of"] == "schedule.create"
    assert specs["ToolSearch"].raw["metadata"]["alias_of"] == "tool.search"
    assert specs["EnterPlanMode"].raw["metadata"]["alias_of"] == "plan.enter"
    assert specs["ExitPlanMode"].raw["metadata"]["alias_of"] == "plan.exit"
    assert specs["Agent"].raw["metadata"]["alias_of"] == "agent.run"
    assert specs["Task"].raw["metadata"]["alias_of"] == "agent.run"
    assert specs["SendMessage"].raw["metadata"]["alias_of"] == "team.send"
    assert specs["TeamCreate"].raw["metadata"]["alias_of"] == "team.create"
    assert specs["TeamDelete"].raw["metadata"]["alias_of"] == "team.delete"
    assert specs["StructuredOutput"].raw["metadata"]["alias_of"] == "structured.output"
    assert specs["Skill"].raw["metadata"]["alias_of"] == "skill.invoke"
    assert specs["LSP"].raw["metadata"]["alias_of"] == "lsp.query"
    assert specs["Config"].raw["metadata"]["alias_of"] == "config.manage"
    assert specs["AskUserQuestion"].raw["metadata"]["alias_of"] == "user.ask"
    assert specs["SendUserMessage"].raw["metadata"]["alias_of"] == "user.message"
    assert specs["Brief"].raw["metadata"]["alias_of"] == "user.message"
    assert specs["EnterWorktree"].raw["metadata"]["alias_of"] == "worktree.enter"
    assert specs["ExitWorktree"].raw["metadata"]["alias_of"] == "worktree.exit"


def test_create_session_enables_structured_output_for_json_schema_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    session = create_agent_session(settings, AgentSpec(metadata={"structured_output_schema": schema}))

    assert session.runtime.enabled_tools == ["StructuredOutput"]
    spec = session.runtime.tools.specs(["StructuredOutput"])[0]
    assert spec.raw["metadata"]["alias_of"] == "structured.output"
    assert spec.parameters == schema


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


def test_create_session_applies_config_overrides_from_session_state(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "base-model"
    store = InMemorySessionStateStore()
    asyncio.run(
        store.save(
            SessionStateRecord(
                tenant_id="default",
                user_id="anonymous",
                agent_id="default",
                workspace_id="default",
                metadata={"config.model": json.dumps("override-model")},
                permission_overridden=True,
                permission_profile_override="plan",
                permission_mode_override="ask",
            )
        )
    )

    session = create_agent_session(settings, AgentSpec(), session_state_store=store)

    assert session.runtime.model == "override-model"
    assert session.tool_context.config_overrides["config.model"] == json.dumps("override-model")
    assert session.tool_context.permission_profile_override == "plan"
    assert session.tool_context.agent_spec.tool_permissions.mode == "ask"


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

    async def fake_load_mcp(settings, registry, roots=None, records=None, oauth_authenticator=None):
        captured["name"] = settings.mcp.SERVER_NAME
        captured["command"] = settings.mcp.SERVER_COMMAND
        captured["execution_mode"] = settings.mcp.EXECUTION_MODE
        captured["sandbox_profile"] = settings.mcp.SANDBOX_PROFILE
        captured["roots"] = list(roots or [])
        captured["records"] = [(record.name, record.enabled) for record in records or []]
        captured["oauth_authenticator"] = oauth_authenticator
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
        await store.save(
            MCPServerRecord(
                name="search",
                command="python search.py",
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

    assert captured["oauth_authenticator"] is not None
    assert {key: value for key, value in captured.items() if key != "oauth_authenticator"} == {
        "name": "search",
        "command": "python search.py",
        "execution_mode": "workspace",
        "sandbox_profile": "coding",
        "roots": [str(session.workspace.path)],
        "records": [("search", True), ("docs", True)],
    }
    assert session.tool_context.mcp_config_store is store


def test_create_session_passes_mcp_elicitation_handler_to_loader(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    captured = {}

    async def fake_load_mcp(settings, registry, roots=None, records=None, elicitation_handler=None, oauth_authenticator=None):
        captured["elicitation_handler"] = elicitation_handler
        captured["oauth_authenticator"] = oauth_authenticator
        return []

    def elicitation_handler(server_name, params):
        return {"action": "decline", "server": server_name, "params": params}

    monkeypatch.setattr("agents.kernel.assembly.session.load_configured_mcp", fake_load_mcp)
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = asyncio.run(
        create_agent_session_async(
            settings,
            AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"),
            mcp_elicitation_handler=elicitation_handler,
        )
    )

    assert captured["elicitation_handler"] is elicitation_handler
    assert captured["oauth_authenticator"] is not None
    assert session.tool_context.mcp_elicitation_handler is elicitation_handler


def test_create_session_loads_cached_mcp_auth_headers(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    captured = {}

    async def fake_load_mcp(settings, registry, roots=None, records=None, auth_headers=None, oauth_authenticator=None):
        captured["auth_headers"] = dict(auth_headers or {})
        captured["oauth_authenticator"] = oauth_authenticator
        return []

    monkeypatch.setattr("agents.kernel.assembly.session.load_configured_mcp", fake_load_mcp)
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    config_store = InMemoryMCPConfigStore()
    auth_store = InMemoryMCPAuthTokenStore()

    async def create():
        await config_store.save(
            MCPServerRecord(
                name="docs",
                command="",
                transport="http",
                url="https://mcp.example.test",
                tenant_id="default",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="default",
            )
        )
        await auth_store.save(
            MCPAuthTokenRecord(
                name="docs",
                access_token="cached",
                tenant_id="default",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="default",
            )
        )
        return await create_agent_session_async(
            settings,
            AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1"),
            mcp_config_store=config_store,
            mcp_auth_store=auth_store,
        )

    session = asyncio.run(create())

    assert captured["auth_headers"] == {"docs": "Bearer cached"}
    assert captured["oauth_authenticator"] is not None
    assert session.tool_context.mcp_auth_store is auth_store


def test_agent_session_close_closes_mcp_providers(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    mcp_client = FakeCloseableMCPClient()

    async def fake_load_mcp(settings, registry, roots=None, records=None, oauth_authenticator=None):
        return [MCPToolProvider(client=mcp_client, server=MCPServerConfig(name="docs"))]

    monkeypatch.setattr("agents.kernel.assembly.session.load_configured_mcp", fake_load_mcp)
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"

    session = asyncio.run(create_agent_session_async(settings, AgentSpec.from_overrides(user_id="user 1", agent_id="agent 1")))
    asyncio.run(session.aclose())

    assert mcp_client.closed is True
    assert session.tool_context.mcp_providers == []


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


def test_async_create_session_loads_sdk_mcp_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.kernel.assembly.session.ModelClient", lambda config: FakeRuntimeClient())
    settings = FakeSettings()
    settings.server.ROOT_PATH = tmp_path
    settings.models.openai.API_KEY = "key"
    settings.models.openai.MODEL = "model"
    store = InMemoryMCPConfigStore()

    async def sdk_mcp_handler(message):
        method = message.get("method")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "sdk-tools", "version": "1.0.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search SDK tools",
                            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        }
                    ]
                },
            }
        if method == "tools/call":
            arguments = dict(message.get("params", {}).get("arguments", {}) or {})
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"content": [{"type": "text", "text": "sdk:%s" % arguments.get("query", "")}]},
            }
        raise AssertionError("unexpected SDK MCP method: %s" % method)

    async def create_and_call():
        await store.save(
            MCPServerRecord(
                name="sdk-tools",
                command="",
                transport="sdk",
                enabled=True,
                tenant_id="local",
            )
        )
        session = await create_agent_session_async(
            settings,
            AgentSpec.from_overrides(workspace_path=str(tmp_path)),
            mcp_config_store=store,
            sdk_mcp_handlers={"sdk-tools": sdk_mcp_handler},
        )
        result = await session.runtime.tools.execute("mcp__sdk-tools__search", {"query": "agents"})
        await session.aclose()
        return session, result

    session, result = asyncio.run(create_and_call())

    assert "mcp__sdk-tools__search" in session.runtime.tools.names()
    assert "mcp__sdk-tools__search" in session.runtime.config.enabled_tools
    assert result.content == "sdk:agents"
