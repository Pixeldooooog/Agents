"""Shared schema bases for the HTTP adapter."""

from pydantic import BaseModel, ConfigDict


class AppSchema(BaseModel):
    """项目通用 Pydantic 基类。"""

    model_config = ConfigDict(extra="ignore")
