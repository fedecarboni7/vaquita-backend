from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory
from app.main import app
from app.models.user import User
from app.services.email import get_email_sender


class FakeEmailSender:
    def __init__(self):
        self.messages = []

    async def __call__(self, to, subject, html, text):
        self.messages.append({"to": to, "subject": subject, "html": html, "text": text})


async def create_user(email: str, *, verified: bool, password_hash: str | None = None) -> User:
    user = User(email=email, google_id=None, email_verified=verified, password_hash=password_hash)
    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.fixture
def fake_sender():
    sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


async def request(client, method, path, **kwargs):
    return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_register_verify_and_login_flow(fake_sender):
    email = f"auth-{uuid4()}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await request(
            client, "POST", "/auth/register", json={"email": email.upper(), "password": "correct horse"}
        )
        assert response.status_code == 202
        assert len(fake_sender.messages) == 1
        token = fake_sender.messages[0]["text"].split("token=", 1)[1]

        verify_response = await request(client, "POST", "/auth/verify-email", json={"token": token})
        assert verify_response.status_code == 200
        login_response = await request(
            client, "POST", "/auth/login", json={"email": email, "password": "correct horse"}
        )
        assert login_response.status_code == 200
        wrong_response = await request(
            client, "POST", "/auth/login", json={"email": email, "password": "wrong password"}
        )
        assert wrong_response.status_code == 401


@pytest.mark.asyncio
async def test_unverified_login_returns_machine_readable_error(fake_sender):
    email = f"pending-{uuid4()}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await request(client, "POST", "/auth/register", json={"email": email, "password": "correct horse"})
        response = await request(client, "POST", "/auth/login", json={"email": email, "password": "correct horse"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "email_not_verified"


@pytest.mark.asyncio
async def test_generic_auth_responses_match_for_existing_and_missing_emails(fake_sender):
    existing_email = f"existing-{uuid4()}@example.com"
    await create_user(existing_email, verified=True)
    missing_email = f"missing-{uuid4()}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        existing = await request(
            client, "POST", "/auth/register", json={"email": existing_email, "password": "correct horse"}
        )
        missing = await request(
            client, "POST", "/auth/register", json={"email": missing_email, "password": "correct horse"}
        )
        assert (existing.status_code, existing.json()) == (missing.status_code, missing.json())

        existing = await request(client, "POST", "/auth/forgot-password", json={"email": existing_email})
        missing = await request(client, "POST", "/auth/forgot-password", json={"email": missing_email})
        assert (existing.status_code, existing.json()) == (missing.status_code, missing.json())


@pytest.mark.asyncio
async def test_set_password_only_allows_google_only_user(fake_sender):
    email = f"google-only-{uuid4()}@example.com"
    user = await create_user(email, verified=True)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await request(
            client, "POST", "/auth/set-password", json={"new_password": "correct horse"}, headers=headers
        )
        second = await request(
            client, "POST", "/auth/set-password", json={"new_password": "another pass"}, headers=headers
        )
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_reset_password_flow(fake_sender):
    email = f"reset-{uuid4()}@example.com"
    user = await create_user(email, verified=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await request(client, "POST", "/auth/forgot-password", json={"email": email})
        token = fake_sender.messages[-1]["text"].split("token=", 1)[1]
        response = await request(
            client, "POST", "/auth/reset-password", json={"token": token, "new_password": "new password"}
        )
        login = await request(client, "POST", "/auth/login", json={"email": email, "password": "new password"})
    assert response.status_code == 200
    assert login.status_code == 200
    assert user is not None
