from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


async def _create_test_user() -> User:
    user = User(
        email=f"available-months-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Available Months Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def _create_account(user_id, name: str) -> Account:
    account = Account(
        user_id=user_id,
        name=name,
        currency="ARS",
    )

    async with async_session_factory() as session:
        session.add(account)
        await session.commit()
        await session.refresh(account)

    return account


async def _create_transaction(
    *,
    user_id,
    account_id,
    amount: float,
    transaction_type: TransactionType,
    expense_date: date,
    account_destination_id=None,
    currency: str = "ARS",
) -> Transaction:
    transaction = Transaction(
        id=uuid4(),
        user_id=user_id,
        account_id=account_id,
        amount=amount,
        currency=currency,
        type=transaction_type,
        expense_date=expense_date,
        description="test",
        account_destination_id=account_destination_id,
        affects_balance=True,
    )

    async with async_session_factory() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

    return transaction


async def _get_available_months(client: AsyncClient, token: str) -> list[str]:
    response = await client.get(
        "/expenses/available-months",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_available_months_returns_all_types_across_months() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    source_account = await _create_account(user.id, "Cuenta Principal")
    destination_account = await _create_account(user.id, "Ahorros")

    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=1200.0,
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 4, 13),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=2000.0,
        transaction_type=TransactionType.income,
        expense_date=date(2026, 5, 1),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=500.0,
        transaction_type=TransactionType.transfer,
        expense_date=date(2026, 5, 3),
        account_destination_id=destination_account.id,
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=300.0,
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 7, 15),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=50.0,
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 7, 31),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        months = await _get_available_months(client, token)

    assert months == ["2026-04", "2026-05", "2026-07"]


@pytest.mark.asyncio
async def test_available_months_returns_empty_list_for_user_without_transactions() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        months = await _get_available_months(client, token)

    assert months == []


@pytest.mark.asyncio
async def test_available_months_does_not_leak_another_users_months() -> None:
    first_user = await _create_test_user()
    second_user = await _create_test_user()
    token = create_access_token(second_user.id)

    first_account = await _create_account(first_user.id, "Cuenta Principal")
    await _create_transaction(
        user_id=first_user.id,
        account_id=first_account.id,
        amount=1200.0,
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 4, 13),
    )
    await _create_transaction(
        user_id=first_user.id,
        account_id=first_account.id,
        amount=900.0,
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 6, 20),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        months = await _get_available_months(client, token)

    assert months == []


@pytest.mark.asyncio
async def test_available_months_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/expenses/available-months")

    assert response.status_code == 401
