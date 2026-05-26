from agents.kernel.capabilities.skill_loading import load_configured_skills, resolve_active_tools
from agents.kernel.capabilities.web import create_web_search_provider

__all__ = [
    "create_web_search_provider",
    "load_configured_mcp",
    "load_configured_skills",
    "resolve_active_tools",
]


def __getattr__(name: str):
    if name == "load_configured_mcp":
        from agents.kernel.mcp.loading import load_configured_mcp

        return load_configured_mcp
    raise AttributeError(name)
