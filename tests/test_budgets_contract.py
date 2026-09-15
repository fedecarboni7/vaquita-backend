from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.budget import Budget
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


async def _create_user(prefix: str) -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.com", google_id=str(uuid4()), display_name=prefix)
    await engine.dispose()
    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _create_category(user_id, name: str = "Comida") -> Category:
    category = Category(id=uuid4(), user_id=user_id, name=name, type="expense")
    async with async_session_factory() as session:
        session.add(category)
        await session.commit()
        await session.refresh(category)
    return category


async def _create_subcategory(user_id, category_id, name: str = "Verduras") -> Subcategory:
    subcategory = Subcategory(id=uuid4(), user_id=user_id, category_id=category_id, name=name)
    async with async_session_factory() as session:
        session.add(subcategory)
        await session.commit()
        await session.refresh(subcategory)
    return subcategory


async def _create_transaction(
    user_id,
    category_id,
    subcategory_id=None,
    amount="10.00",
    currency="ARS",
    transaction_type=TransactionType.expense,
    affects_balance=True,
) -> Transaction:
    transaction = Transaction(
        id=uuid4(),
        user_id=user_id,
        amount=Decimal(amount),
        currency=currency,
        type=transaction_type,
        category_id=category_id,
        subcategory_id=subcategory_id,
        account_id=None,
        account_destination_id=None,
        expense_date=date.today(),
        affects_balance=affects_balance,
    )
    async with async_session_factory() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)
    return transaction


@pytest.mark.asyncio
async def test_budget_crud_and_live_spending() -> None:
    user = await _create_user("budget-crud")
    category = await _create_category(user.id)
    await _create_transaction(user.id, category.id, amount="25.00")
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/budgets",
            json={"category_id": str(category.id), "amount": "100.00", "currency": "ARS"},
            headers=headers,
        )
        assert create_response.status_code == 201
        budget = create_response.json()
        assert budget["spent"] == "25.00"
        assert budget["remaining"] == "75.00"
        assert budget["percentage"] == 25.0

        list_response = await client.get("/budgets", headers=headers)
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        patch_response = await client.patch(
            f"/budgets/{budget['id']}",
            json={"amount": "50.00"},
            headers=headers,
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["remaining"] == "25.00"

        delete_response = await client.delete(f"/budgets/{budget['id']}", headers=headers)
        assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_budget_scope_additive_and_duplicate_rejection() -> None:
    user = await _create_user("budget-scope")
    category = await _create_category(user.id)
    subcategory = await _create_subcategory(user.id, category.id)
    await _create_transaction(user.id, category.id, amount="10.00")
    await _create_transaction(user.id, category.id, subcategory.id, amount="20.00")
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        category_response = await client.post(
            "/budgets",
            json={"category_id": str(category.id), "amount": "100.00", "currency": "ARS"},
            headers=headers,
        )
        assert category_response.status_code == 201
        assert category_response.json()["spent"] == "30.00"

        duplicate_response = await client.post(
            "/budgets",
            json={"category_id": str(category.id), "amount": "200.00", "currency": "ARS"},
            headers=headers,
        )
        assert duplicate_response.status_code == 400

        subcategory_response = await client.post(
            "/budgets",
            json={
                "category_id": str(category.id),
                "subcategory_id": str(subcategory.id),
                "amount": "50.00",
                "currency": "ARS",
            },
            headers=headers,
        )
        assert subcategory_response.status_code == 201
        assert subcategory_response.json()["spent"] == "20.00"

        budgets_response = await client.get("/budgets", headers=headers)
        values = {item["subcategory_id"]: item["spent"] for item in budgets_response.json()}
        assert values[None] == "30.00"
        assert values[str(subcategory.id)] == "20.00"


@pytest.mark.asyncio
async def test_budget_ignores_income_transfer_disabled_and_other_currency() -> None:
    user = await _create_user("budget-filters")
    category = await _create_category(user.id)
    await _create_transaction(user.id, category.id, amount="10.00")
    await _create_transaction(user.id, category.id, amount="20.00", transaction_type=TransactionType.income)
    await _create_transaction(user.id, category.id, amount="30.00", transaction_type=TransactionType.transfer)
    await _create_transaction(user.id, category.id, amount="40.00", affects_balance=False)
    await _create_transaction(user.id, category.id, amount="50.00", currency="USD")
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/budgets",
            json={"category_id": str(category.id), "amount": "100.00", "currency": "ARS"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert create_response.status_code == 201
    assert create_response.json()["spent"] == "10.00"


@pytest.mark.asyncio
async def test_budget_ownership_isolation() -> None:
    owner = await _create_user("budget-owner")
    other_user = await _create_user("budget-other")
    category = await _create_category(owner.id)
    token = create_access_token(owner.id)
    other_token = create_access_token(other_user.id)
    headers = {"Authorization": f"Bearer {token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/budgets",
            json={"category_id": str(category.id), "amount": "100.00"},
            headers=headers,
        )
        budget_id = create_response.json()["id"]

        list_response = await client.get("/budgets", headers=other_headers)
        assert list_response.status_code == 200
        assert list_response.json() == []

        patch_response = await client.patch(
            f"/budgets/{budget_id}",
            json={"amount": "50.00"},
            headers=other_headers,
        )
        assert patch_response.status_code == 404

        delete_response = await client.delete(f"/budgets/{budget_id}", headers=other_headers)
        assert delete_response.status_code == 404


@pytest.mark.asyncio
async def test_subcategory_delete_is_blocked_by_budget() -> None:
    user = await _create_user("budget-delete-guard")
    category = await _create_category(user.id)
    subcategory = await _create_subcategory(user.id, category.id)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    async with async_session_factory() as session:
        session.add(
            Budget(
                id=uuid4(),
                user_id=user.id,
                category_id=category.id,
                subcategory_id=subcategory.id,
                amount=Decimal("100.00"),
                currency="ARS",
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        blocked_response = await client.delete(
            f"/categories/{category.id}/subcategories/{subcategory.id}",
            headers=headers,
        )
        assert blocked_response.status_code == 400

        async with async_session_factory() as session:
            budget_id = await session.scalar(select(Budget.id).where(Budget.subcategory_id == subcategory.id))

        await client.delete(f"/budgets/{budget_id}", headers=headers)
        allowed_response = await client.delete(
            f"/categories/{category.id}/subcategories/{subcategory.id}",
            headers=headers,
        )
        assert allowed_response.status_code == 204
