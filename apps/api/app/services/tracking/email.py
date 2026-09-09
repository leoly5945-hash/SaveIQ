"""Pluggable outbound email for price alerts (CP15).

``EMAIL_SENDER`` picks the transport: ``console`` (structured-log, the default),
``null`` (drop), or ``smtp`` (real send via ``SMTP_*``). A misconfigured ``smtp``
falls back to ``console`` with a warning so a cron run never crashes on it.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeEmailMessage
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


class SmtpEmailSender:
    """Sends via SMTP + STARTTLS (works with Gmail app passwords, SES, Resend…)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        timeout: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        mime = MimeEmailMessage()
        mime["From"] = message.from_email
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as client:
            client.ehlo()
            if self._use_tls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if self._username and self._password:
                client.login(self._username, self._password)
            client.send_message(mime)


def get_email_sender(settings: Settings | None = None) -> EmailSender:
    settings = settings or get_settings()
    if settings.email_sender == "null":
        return NullEmailSender()
    if settings.email_sender == "smtp":
        if settings.smtp_host:
            return SmtpEmailSender(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                use_tls=settings.smtp_use_tls,
            )
        logger.warning("EMAIL_SENDER=smtp but SMTP_HOST is unset — using console sender")
    return ConsoleEmailSender()
