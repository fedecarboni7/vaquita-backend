import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
EmailSender = Callable[[str, str, str, str], Awaitable[None]]


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    if not settings.BREVO_API_KEY:
        logger.info("Email local: asunto=%s texto=%s", subject, text)
        return

    payload = {
        "sender": {"name": settings.MAIL_FROM_NAME, "email": settings.MAIL_FROM_EMAIL},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": settings.BREVO_API_KEY},
            json=payload,
        )
        response.raise_for_status()


async def send_email_safely(sender: EmailSender, to: str, subject: str, html: str, text: str) -> None:
    try:
        await sender(to, subject, html, text)
    except Exception:
        logger.exception("No se pudo enviar el email de asunto %s a %s", subject, to)


async def get_email_sender() -> EmailSender:
    return send_email
