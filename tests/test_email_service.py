import logging

import pytest

from app.config import settings
from app.services.email import send_email


@pytest.mark.asyncio
async def test_missing_brevo_key_does_not_log_email_content_outside_development(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    with caplog.at_level(logging.WARNING, logger="app.services.email"):
        await send_email("user@example.com", "Sensitive subject", "<p>secret</p>", "token=secret-token")

    assert "BREVO_API_KEY" in caplog.text
    assert "Sensitive subject" not in caplog.text
    assert "secret-token" not in caplog.text
    assert "[DEV EMAIL]" not in caplog.text


@pytest.mark.asyncio
async def test_missing_brevo_key_logs_email_content_in_development(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    with caplog.at_level(logging.WARNING, logger="app.services.email"):
        await send_email("user@example.com", "Development subject", "<p>secret</p>", "token=dev-token")

    assert "[DEV EMAIL]" in caplog.text
    assert "Development subject" in caplog.text
    assert "dev-token" in caplog.text
