from agents.entrypoints.smoke import run_smoke


def test_delivery_smoke_checks_server_tools_git_test_and_runtime():
    checks = run_smoke()

    assert {check.name for check in checks} == {
        "server",
        "filesystem",
        "search",
        "test",
        "git",
        "runtime",
        "cleanup",
    }
