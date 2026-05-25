from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import Settings


def send_email(settings: Settings, subject: str, markdown: str) -> None:
    missing = [
        name
        for name, value in {
            "SMTP_HOST": settings.smtp_host,
            "SMTP_USER": settings.smtp_user,
            "SMTP_PASSWORD": settings.smtp_password,
            "REPORT_RECIPIENT": settings.report_recipient,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing email settings: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_user
    message["To"] = settings.report_recipient
    message.set_content(markdown)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
