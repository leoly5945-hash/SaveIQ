"""Placeholder long-running worker for staging infrastructure validation."""

from __future__ import annotations

import logging
import time

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("Starting placeholder worker for %s", settings.app_name)

    while True:
        logger.info("Placeholder worker heartbeat")
        time.sleep(300)


if __name__ == "__main__":
    main()
