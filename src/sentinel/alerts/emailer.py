"""Send an alert email over SMTP (standard library only)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sentinel.alerts.errors import AlertError
from sentinel.config.models import EmailAlert


def send(settings: EmailAlert, subject: str, body: str, timeout: float = 10) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.from_address or settings.username or "sentinel@localhost"
    message["To"] = ", ".join(settings.to)
    message.set_content(body)

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
                _deliver(smtp, settings, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
                if settings.use_tls:
                    smtp.starttls()
                _deliver(smtp, settings, message)
    except (smtplib.SMTPException, OSError) as exc:
        raise AlertError(f"email to {message['To']} failed: {exc}") from None


def _deliver(smtp: smtplib.SMTP, settings: EmailAlert, message: EmailMessage) -> None:
    if settings.username and settings.password:
        smtp.login(settings.username, settings.password)
    smtp.send_message(message)
