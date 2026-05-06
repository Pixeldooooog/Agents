"""Application bootstrap hooks for the FastAPI interface."""

from agents.interfaces.server.bootstrap.exceptions import register_exception
from agents.interfaces.server.bootstrap.hooks import register_hook
from agents.interfaces.server.bootstrap.middleware import register_middleware

__all__ = ["register_exception", "register_hook", "register_middleware"]
