from __future__ import annotations

import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _load_encryption_key() -> bytes:
    key_hex = settings.ENCRYPTION_KEY.strip()
    if not key_hex:
        raise ValueError("ENCRYPTION_KEY is not configured")

    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise ValueError("ENCRYPTION_KEY must be a valid hex string") from exc

    if len(key) != 32:
        raise ValueError("ENCRYPTION_KEY must be 32 bytes in hex format")

    return key


def encrypt_key(api_key: str) -> str:
    key = _load_encryption_key()
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, api_key.encode("utf-8"), None)
    payload = nonce + ciphertext
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def decrypt_key(encrypted_key: str) -> str:
    key = _load_encryption_key()
    try:
        payload = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid encrypted key payload") from exc

    if len(payload) < 13:
        raise ValueError("Invalid encrypted key payload")

    nonce = payload[:12]
    ciphertext = payload[12:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
