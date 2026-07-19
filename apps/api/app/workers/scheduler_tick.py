"""Placeholder scheduler task for staging infrastructure validation."""

from __future__ import annotations

import logging

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("Placeholder scheduler tick completed for %s", settings.app_name)


if __name__ == "__main__":
    main()
