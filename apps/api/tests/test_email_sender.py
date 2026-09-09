"""Tests for the pluggable price-alert email transport (checklist item 4)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.settings import Settings
from app.services.tracking import email as email_mod
from app.services.tracking.email import (
    ConsoleEmailSender,
    EmailMessage,
    NullEmailSender,
    SmtpEmailSender,
    get_email_sender,
)

MSG = EmailMessage(
    to="shopper@example.com",
    subject="Price drop: Widget",
    text_body="It dropped.",
    from_email="alerts@saveiq.ca",
)


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: float = 0) -> None:
        self.host = host
        self.port = port
        self.calls: list[str] = []
        self.sent: list[Any] = []
        self.login_args: tuple[str, str] | None = None
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self, context: object = None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, mime: Any) -> None:
        self.sent.append(mime)


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSMTP.instances.clear()


def test_smtp_sender_starttls_login_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    sender = SmtpEmailSender(
        host="smtp.example.com",
        port=587,
        username="u",
        password="p",
        use_tls=True,
    )
    sender.send(MSG)

    smtp = FakeSMTP.instances[-1]
    assert smtp.host == "smtp.example.com" and smtp.port == 587
    assert "starttls" in smtp.calls
    assert smtp.login_args == ("u", "p")
    assert len(smtp.sent) == 1
    mime = smtp.sent[0]
    assert mime["To"] == "shopper@example.com"
    assert mime["Subject"] == "Price drop: Widget"
    assert "It dropped." in mime.get_content()


def test_smtp_sender_skips_login_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    SmtpEmailSender(host="h", port=25, username=None, password=None, use_tls=False).send(MSG)
    smtp = FakeSMTP.instances[-1]
    assert smtp.login_args is None
    assert "starttls" not in smtp.calls
    assert len(smtp.sent) == 1


def test_get_email_sender_selection() -> None:
    assert isinstance(get_email_sender(Settings(EMAIL_SENDER="null")), NullEmailSender)
    assert isinstance(get_email_sender(Settings(EMAIL_SENDER="console")), ConsoleEmailSender)
    # smtp requested but not configured -> console fallback, no crash.
    assert isinstance(get_email_sender(Settings(EMAIL_SENDER="smtp")), ConsoleEmailSender)
    assert isinstance(
        get_email_sender(Settings(EMAIL_SENDER="smtp", SMTP_HOST="smtp.example.com")),
        SmtpEmailSender,
    )
