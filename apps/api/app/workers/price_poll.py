"""CP15 — daily price-poll + alert cycle entrypoint.

Wire this to a Render cron once the blueprint gains a cron service:

    python -m app.workers.price_poll

It re-checks every tracked product, records an observation, and emails any due
price alerts (one-shot). Safe to run repeatedly — observations dedupe on
``(tracked_product_id, observed_at)``.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.providers import build_default_registry
from app.services.tracking.email import get_email_sender
from app.services.tracking.service import run_alert_cycle

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    registry = build_default_registry(settings)
    if len(registry) == 0:
        logger.warning("price poll: no providers configured, nothing to do")
        return

    session = SessionLocal()
    try:
        stats = await run_alert_cycle(
            session,
            registry,
            email_sender=get_email_sender(settings),
            settings=settings,
        )
        session.commit()
        logger.info(
            "price poll cycle complete",
            extra={
                "tracked_checked": stats.tracked_checked,
                "observations_recorded": stats.observations_recorded,
                "alerts_fired": stats.alerts_fired,
                "emails_sent": stats.emails_sent,
                "errors": stats.errors,
            },
        )
    finally:
        session.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
