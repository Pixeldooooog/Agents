"""Builtin tool package entrypoint.

Concrete tool schemas and handlers live in their domain modules. Package-level
imports intentionally expose only the registry assembly entry to avoid another
large compatibility export surface.
"""

from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.registration import register_builtin_tools


__all__ = ["register_builtin_tools"]
