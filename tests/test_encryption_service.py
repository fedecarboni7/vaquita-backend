import pytest

from app.config import settings
from app.services.encryption import decrypt_key, encrypt_key


def test_encrypt_decrypt_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "00" * 32)

    encrypted = encrypt_key("secret-api-key")

    assert encrypted != "secret-api-key"
    assert decrypt_key(encrypted) == "secret-api-key"


def test_encrypt_key_raises_for_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "abcd")

    with pytest.raises(ValueError, match="ENCRYPTION_KEY must be 32 bytes"):
        encrypt_key("secret-api-key")
