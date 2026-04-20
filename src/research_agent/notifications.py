from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import Settings


def send_password_reset_email(
    settings: Settings,
    *,
    recipient: str,
    reset_url: str,
    ttl_minutes: int,
) -> None:
    if not settings.smtp_is_configured:
        raise RuntimeError("SMTP is not configured for password reset emails.")

    message = EmailMessage()
    message["Subject"] = "Reset your Economic Research Platform password"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                "A password reset was requested for your Economic Research Platform account.",
                "",
                f"Open this link within {ttl_minutes} minutes: {reset_url}",
                "",
                "If you did not request this change, you can ignore this email.",
            ]
        )
    )

    if settings.smtp_uses_ssl:
        client_factory = smtplib.SMTP_SSL
    else:
        client_factory = smtplib.SMTP

    with client_factory(settings.smtp_host, settings.smtp_port, timeout=20) as client:
        if settings.smtp_security == "starttls":
            client.starttls()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
