from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.category import Category
from app.models.user import User


async def _create_test_user() -> User:
    user = User(
        email=f"edit-category-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Edit Category Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def _create_category(user_id, name: str, category_type: str = "expense") -> Category:
    category = Category(
        id=uuid4(),
        user_id=user_id,
        name=name,
        type=category_type,
    )

    async with async_session_factory() as session:
        session.add(category)
        await session.commit()
        await session.refresh(category)

    return category


@pytest.mark.asyncio
async def test_patch_category_requires_authentication() -> None:
    category_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(f"/categories/{category_id}", json={"name": "Comida"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_category_trims_name() -> None:
    user = await _create_test_user()
    category = await _create_category(user.id, "Comida")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{category.id}",
            json={"name": "  Supermercado  "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Supermercado"


@pytest.mark.asyncio
async def test_patch_category_allows_case_only_change() -> None:
    user = await _create_test_user()
    category = await _create_category(user.id, "comida")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{category.id}",
            json={"name": "Comida"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Comida"


@pytest.mark.asyncio
async def test_patch_category_allows_duplicate_name_across_types() -> None:
    user = await _create_test_user()
    await _create_category(user.id, "Comida", "expense")
    target = await _create_category(user.id, "Salario", "income")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{target.id}",
            json={"name": "  comida  "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "comida"


@pytest.mark.asyncio
async def test_patch_category_rejects_duplicate_name_same_type() -> None:
    user = await _create_test_user()
    await _create_category(user.id, "Comida", "expense")
    target = await _create_category(user.id, "Salario", "expense")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{target.id}",
            json={"name": "  comida  "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe una categoria con ese nombre"
