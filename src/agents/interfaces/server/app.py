# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：app.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents.interfaces.server.api.router import api_router
from agents.interfaces.server.core.config import settings
from agents.interfaces.server.bootstrap import register_exception, register_hook, register_middleware
from agents.interfaces.server.core.logging import logger
from agents.interfaces.server.static import register_web_ui


@asynccontextmanager
async def lifespan(server: FastAPI):
    """应用生命周期管理。"""
    setattr(server, "logger", logger)
    yield

    logger.info("Application shutdown complete.")


def create_app() -> FastAPI:
    """生成 FastAPI 应用对象。"""
    application = FastAPI(
        debug=settings.server.DEBUG,
        title=settings.server.PROJECT_NAME,
        lifespan=lifespan,
        openapi_url="/openapi.json" if settings.server.ENABLE_SWAGGER_DOC else None,
        docs_url="/docs" if settings.server.ENABLE_SWAGGER_DOC else None,
        redoc_url="/redoc" if settings.server.ENABLE_SWAGGER_DOC else None,
        routes=api_router.routes,
    )

    register_web_ui(application)
    register_middleware(application)
    register_exception(application)
    register_hook(application)
    return application


app = create_app()
