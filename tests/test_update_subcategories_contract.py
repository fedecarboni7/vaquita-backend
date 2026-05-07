from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.user import User


async def _create_test_user() -> User:
    user = User(
        email=f"edit-subcategory-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Edit Subcategory Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def _create_category(user_id, name: str) -> Category:
    category = Category(
        id=uuid4(),
        user_id=user_id,
        name=name,
        type="expense",
    )

    async with async_session_factory() as session:
        session.add(category)
        await session.commit()
        await session.refresh(category)

    return category


async def _create_subcategory(user_id, category_id, name: str) -> Subcategory:
    subcategory = Subcategory(
        id=uuid4(),
        user_id=user_id,
        category_id=category_id,
        name=name,
    )

    async with async_session_factory() as session:
        session.add(subcategory)
        await session.commit()
        await session.refresh(subcategory)

    return subcategory


@pytest.mark.asyncio
async def test_patch_subcategory_requires_authentication() -> None:
    category_id = uuid4()
    subcategory_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{category_id}/subcategories/{subcategory_id}",
            json={"name": "Verduras"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_subcategory_trims_name() -> None:
    user = await _create_test_user()
    category = await _create_category(user.id, "Comida")
    subcategory = await _create_subcategory(user.id, category.id, "Verduras")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{category.id}/subcategories/{subcategory.id}",
            json={"name": "  Verduras y frutas  "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Verduras y frutas"


@pytest.mark.asyncio
async def test_patch_subcategory_rejects_duplicate_name_in_category() -> None:
    user = await _create_test_user()
    category = await _create_category(user.id, "Comida")
    await _create_subcategory(user.id, category.id, "Verduras")
    target = await _create_subcategory(user.id, category.id, "Frutas")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/categories/{category.id}/subcategories/{target.id}",
            json={"name": " verduras "},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe una subcategoria con ese nombre"
