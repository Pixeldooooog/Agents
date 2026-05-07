from __future__ import annotations

import warnings

import uvicorn

from agents.interfaces.server.app import app
from agents.interfaces.server.core.config import settings
from agents.interfaces.server.core.logging import logger
from agents.interfaces.server.utils import utils

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


def main(*, show_settings: bool = True) -> None:
    if show_settings:
        utils.print_info(settings, logger)
    uvicorn.run(
        "agents.interfaces.server.app:app" if settings.server.DEBUG else app,
        host=settings.server.HOST,
        port=settings.server.PORT,
        reload=settings.server.DEBUG and settings.server.WORKERS == 1,
        workers=settings.server.WORKERS,
        lifespan="on",
        log_config=utils.set_uvicorn_logger(settings.log.LOGGER_FORMAT),
    )


if __name__ == "__main__":
    main()
