import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

password_hasher = PasswordHasher()
_dummy_password_hash: str | None = None


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(password_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        return await asyncio.to_thread(password_hasher.verify, password_hash, password)
    except (VerificationError, VerifyMismatchError):
        return False


async def verify_dummy_password(password: str) -> bool:
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = await hash_password("vaquita-dummy-password-for-timing")
    return await verify_password(password, _dummy_password_hash)
