from dataclasses import dataclass
from html import escape
from urllib.parse import quote

from app.config import settings


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    text: str


def _link(path: str, raw_token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/{path}?token={quote(raw_token)}"


def verification_email(raw_token: str) -> EmailContent:
    link = _link("verify-email", raw_token)
    safe_link = escape(link)
    return EmailContent(
        subject="Verificá tu mail en vaquita",
        html=f'<p>Hola,</p><p>Verificá tu mail para empezar a usar vaquita:</p><p><a href="{safe_link}">Verificar mi mail</a></p>',
        text=f"Hola,\n\nVerificá tu mail para empezar a usar vaquita:\n{link}",
    )


def password_reset_email(raw_token: str) -> EmailContent:
    link = _link("reset-password", raw_token)
    safe_link = escape(link)
    return EmailContent(
        subject="Restablecé tu contraseña de vaquita",
        html=f'<p>Hola,</p><p>Usá este link para elegir una nueva contraseña:</p><p><a href="{safe_link}">Restablecer contraseña</a></p>',
        text=f"Hola,\n\nUsá este link para elegir una nueva contraseña:\n{link}",
    )
