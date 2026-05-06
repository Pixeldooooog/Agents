"""Middleware registration for the FastAPI interface."""

from fastapi import FastAPI

from agents.interfaces.server.core.middleware import register_middleware as _register_middleware


def register_middleware(app: FastAPI) -> None:
    """注册跨域和鉴权中间件。"""
    _register_middleware(app)
