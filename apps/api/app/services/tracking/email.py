"""Pluggable outbound email for price alerts (CP15).

MVP ships ``console`` (structured-log) and ``null`` senders. A real SMTP / API
sender is added behind ``EMAIL_SENDER`` later without touching callers.
"""

from __future__ import annotations

import logging
from typing import Protocol

from pydantic import BaseModel

from app.core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailMessage(BaseModel):
    to: str
    subject: str
    text_body: str
    from_email: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver ``message`` (or record the intent to)."""


class ConsoleEmailSender:
    """Logs the email instead of sending it — the staging default."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email (console sender)",
            extra={
                "to": message.to,
                "from": message.from_email,
                "subject": message.subject,
                "body": message.text_body,
            },
        )


class NullEmailSender:
    """Drops the email. For tests / disabled environments."""

    def send(self, message: EmailMessage) -> None:  # pragma: no cover - trivial
        return None


def get_email_sender(settings: Settings | None = None) -> EmailSender:
    settings = settings or get_settings()
    if settings.email_sender == "null":
        return NullEmailSender()
    return ConsoleEmailSender()
