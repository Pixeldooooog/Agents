from agents.entrypoints.agents import _repo_root


def test_agents_entrypoint_resolves_repository_root():
    root = _repo_root()

    assert (root / "apps" / "terminal").is_dir()
    assert (root / "src" / "agents").is_dir()
