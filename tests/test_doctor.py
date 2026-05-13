from types import SimpleNamespace

from agents.entrypoints.doctor import run_doctor
from agents.kernel.config.profiles import ModelProfile


def test_doctor_reports_readiness_without_leaking_keys(tmp_path):
    (tmp_path / "apps" / "terminal").mkdir(parents=True)
    (tmp_path / "apps" / "terminal" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "apps" / "web" / "dist").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "apps" / "web" / "dist" / "index.html").write_text("", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
    settings = SimpleNamespace(
        server=SimpleNamespace(HOST="127.0.0.1", PORT=8020, API_PREFIX="/api"),
        agent=SimpleNamespace(
            WORKSPACE_ROOT=".agents/workspaces",
            RUN_STORE="sqlite",
            DB_PATH=".agents/agents.db",
            SANDBOX_PROVIDER="local",
            SANDBOX_PROFILE="coding",
            HTTPS_PROXY="",
            ALL_PROXY="",
            HTTP_PROXY="",
        ),
        web_search=SimpleNamespace(PROVIDER="tavily", TAVILY_API_KEY="secret"),
    )
    profiles = [
        ModelProfile(
            name="openai-chat",
            protocol="openai-chat",
            model="gpt-test",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )
    ]

    checks = run_doctor(
        repo_root=tmp_path,
        settings=settings,
        model_profiles=profiles,
        command_lookup=lambda command: "/usr/bin/%s" % command,
        env_file=env_file,
    )

    rendered = "\n".join(check.detail for check in checks)
    assert {check.status for check in checks} == {"ready"}
    assert "secret" not in rendered
    assert "openai-chat/openai-chat@gpt-test" not in rendered
    assert "openai-chat=gpt-test" not in rendered
    assert "openai-chat=openai-chat/gpt-test@api.example.com" in rendered


def test_doctor_fails_when_no_model_profile_is_configured(tmp_path):
    settings = SimpleNamespace(
        server=SimpleNamespace(HOST="127.0.0.1", PORT=8020, API_PREFIX="/api"),
        agent=SimpleNamespace(
            WORKSPACE_ROOT=".agents/workspaces",
            RUN_STORE="memory",
            DB_PATH=".agents/agents.db",
            SANDBOX_PROVIDER="local",
            SANDBOX_PROFILE="restricted",
            HTTPS_PROXY="",
            ALL_PROXY="",
            HTTP_PROXY="",
        ),
        web_search=SimpleNamespace(PROVIDER="none", TAVILY_API_KEY=""),
    )

    checks = run_doctor(
        repo_root=tmp_path,
        settings=settings,
        model_profiles=[],
        command_lookup=lambda command: None,
        env_file=tmp_path / ".env",
    )

    assert any(check.name == "models" and check.status == "fail" for check in checks)


def test_doctor_fails_when_project_proxy_port_is_not_listening(tmp_path):
    settings = SimpleNamespace(
        server=SimpleNamespace(HOST="127.0.0.1", PORT=8020, API_PREFIX="/api"),
        agent=SimpleNamespace(
            WORKSPACE_ROOT=".agents/workspaces",
            RUN_STORE="memory",
            DB_PATH=".agents/agents.db",
            SANDBOX_PROVIDER="local",
            SANDBOX_PROFILE="restricted",
            HTTPS_PROXY="http://127.0.0.1:7890",
            ALL_PROXY="",
            HTTP_PROXY="",
        ),
        web_search=SimpleNamespace(PROVIDER="none", TAVILY_API_KEY=""),
    )
    profiles = [
        ModelProfile(
            name="openai-chat",
            protocol="openai-chat",
            model="gpt-test",
            base_url="https://api.example.com/v1",
            api_key="secret",
        )
    ]

    checks = run_doctor(
        repo_root=tmp_path,
        settings=settings,
        model_profiles=profiles,
        command_lookup=lambda command: None,
        tcp_connect=lambda host, port, timeout: False,
        env_file=tmp_path / ".env",
    )

    proxy_check = next(check for check in checks if check.name == "proxy")
    assert proxy_check.status == "fail"
    assert "AGENT_HTTPS_PROXY 127.0.0.1:7890 is not listening" in proxy_check.detail
    assert "shell proxy env" in proxy_check.detail
