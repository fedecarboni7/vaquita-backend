from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.user import User


async def _create_test_user() -> User:
    user = User(
        email=f"delete-account-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Delete Account Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


@pytest.mark.asyncio
async def test_delete_account_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_account_returns_204_for_authenticated_user() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_token_is_rejected_after_account_deletion() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        delete_response = await client.delete(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_response.status_code == 204

        expenses_response = await client.get(
            "/expenses",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert expenses_response.status_code == 401
