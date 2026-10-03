from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.auth_token import AuthToken
from app.services.auth_tokens import (
    EMAIL_VERIFICATION_PURPOSE,
    PASSWORD_RESET_PURPOSE,
    TOKEN_LIFETIMES,
    consume_token,
    hash_token,
    issue_token,
)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, token=None):
        self.token = token
        self.added = []
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        return FakeResult(self.token)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_issue_token_stores_only_hash_and_invalidates_previous_tokens():
    session = FakeSession()
    raw_token = await issue_token(session, uuid4(), EMAIL_VERIFICATION_PURPOSE)

    stored = session.added[0]
    assert isinstance(stored, AuthToken)
    assert stored.token_hash == hash_token(raw_token)
    assert stored.token_hash != raw_token
    assert stored.expires_at > datetime.now(timezone.utc)
    assert session.executed


@pytest.mark.asyncio
async def test_consume_token_rejects_expired_and_used_tokens():
    now = datetime.now(timezone.utc)
    expired = AuthToken(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=hash_token("expired"),
        purpose=PASSWORD_RESET_PURPOSE,
        expires_at=now - timedelta(seconds=1),
    )
    assert await consume_token(FakeSession(expired), "expired", PASSWORD_RESET_PURPOSE) is None

    used = AuthToken(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=hash_token("used"),
        purpose=PASSWORD_RESET_PURPOSE,
        expires_at=now + TOKEN_LIFETIMES[PASSWORD_RESET_PURPOSE],
        used_at=now,
    )
    assert await consume_token(FakeSession(used), "used", PASSWORD_RESET_PURPOSE) is None
