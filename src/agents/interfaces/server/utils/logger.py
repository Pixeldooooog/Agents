# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：logger.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# 2026/04/27   Deprecated: moved to server.core.logging
# =====================================================

import warnings

warnings.warn(
    "agents.interfaces.server.utils.logger is deprecated, use agents.interfaces.server.core.logging",
    DeprecationWarning,
    stacklevel=2,
)

from agents.interfaces.server.core.logging import *  # noqa: F401,F403
