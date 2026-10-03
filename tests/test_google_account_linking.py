from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_factory
from app.main import app
from app.models.user import User
from app.routers import auth


async def create_user(email: str, *, verified: bool, password_hash: str | None = None) -> User:
    user = User(email=email, google_id=None, email_verified=verified, password_hash=password_hash)
    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_google_login_links_to_existing_email_account(monkeypatch):
    email = f"linked-{uuid4()}@example.com"
    user = await create_user(email, verified=True, password_hash="existing-hash")

    async def fake_verify(_credential):
        return {"sub": f"google-{uuid4()}", "email": email.upper(), "email_verified": True, "name": "Google User"}

    monkeypatch.setattr(auth, "verify_google_token", fake_verify)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/google", json={"credential": "credential"})
    assert response.status_code == 200

    async with async_session_factory() as session:
        linked = await session.get(User, user.id)
    assert linked is not None
    assert linked.google_id is not None
    assert linked.password_hash == "existing-hash"


@pytest.mark.asyncio
async def test_google_login_clears_unverified_password_before_linking(monkeypatch):
    email = f"hijack-{uuid4()}@example.com"
    user = await create_user(email, verified=False, password_hash="untrusted-hash")

    async def fake_verify(_credential):
        return {"sub": f"google-{uuid4()}", "email": email, "email_verified": True, "name": "Owner"}

    monkeypatch.setattr(auth, "verify_google_token", fake_verify)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/google", json={"credential": "credential"})
    assert response.status_code == 200

    async with async_session_factory() as session:
        linked = await session.get(User, user.id)
    assert linked is not None
    assert linked.email_verified is True
    assert linked.password_hash is None
