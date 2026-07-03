import csv
import io
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.account import Account
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


async def _create_test_user() -> User:
    user = User(
        email=f"export-csv-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Export CSV Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def _create_account(user_id, name: str, currency: str) -> Account:
    account = Account(
        user_id=user_id,
        name=name,
        currency=currency,
    )

    async with async_session_factory() as session:
        session.add(account)
        await session.commit()
        await session.refresh(account)

    return account


async def _create_category(user_id, name: str, category_type: str) -> Category:
    category = Category(
        user_id=user_id,
        name=name,
        type=category_type,
    )

    async with async_session_factory() as session:
        session.add(category)
        await session.commit()
        await session.refresh(category)

    return category


async def _create_subcategory(user_id, category_id, name: str) -> Subcategory:
    subcategory = Subcategory(
        user_id=user_id,
        category_id=category_id,
        name=name,
    )

    async with async_session_factory() as session:
        session.add(subcategory)
        await session.commit()
        await session.refresh(subcategory)

    return subcategory


async def _create_transaction(
    *,
    user_id,
    account_id,
    amount: float,
    currency: str,
    transaction_type: TransactionType,
    expense_date: date,
    description: str,
    category_id=None,
    subcategory_id=None,
    account_destination_id=None,
    to_amount=None,
    created_at: datetime,
) -> Transaction:
    transaction = Transaction(
        id=uuid4(),
        user_id=user_id,
        account_id=account_id,
        amount=amount,
        currency=currency,
        type=transaction_type,
        expense_date=expense_date,
        description=description,
        category_id=category_id,
        subcategory_id=subcategory_id,
        account_destination_id=account_destination_id,
        to_amount=to_amount,
        affects_balance=True,
        created_at=created_at,
        updated_at=created_at,
    )

    async with async_session_factory() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

    return transaction


def _read_csv_rows(response_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response_text)))


@pytest.mark.asyncio
async def test_transactions_export_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/expenses/export")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_transactions_export_returns_header_only_for_empty_list() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/expenses/export",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = _read_csv_rows(response.text)

    assert rows == [
        [
            "date",
            "type",
            "amount",
            "currency",
            "account_name",
            "category_name",
            "subcategory_name",
            "account_destination_name",
            "to_amount",
            "to_currency",
            "description",
        ]
    ]


@pytest.mark.asyncio
async def test_transactions_export_csv_formats_all_transaction_types_and_order() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    source_account = await _create_account(user.id, "Cuenta Principal", "ARS")
    destination_account = await _create_account(user.id, "Ahorros USD", "USD")
    category = await _create_category(user.id, "Comida", "expense")
    subcategory = await _create_subcategory(user.id, category.id, "Supermercado")

    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=50.0,
        currency="ARS",
        transaction_type=TransactionType.transfer,
        expense_date=date(2026, 5, 3),
        description="Transferencia con, coma",
        account_destination_id=destination_account.id,
        to_amount=0.04,
        created_at=datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=1234.56,
        currency="ARS",
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 5, 1),
        description='Pan "casero" y café',
        category_id=category.id,
        subcategory_id=subcategory.id,
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=2000.0,
        currency="ARS",
        transaction_type=TransactionType.income,
        expense_date=date(2026, 5, 2),
        description="Sueldo",
        category_id=category.id,
        subcategory_id=None,
        created_at=datetime(2026, 5, 2, 11, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/expenses/export",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    rows = _read_csv_rows(response.text)

    assert rows[0] == [
        "date",
        "type",
        "amount",
        "currency",
        "account_name",
        "category_name",
        "subcategory_name",
        "account_destination_name",
        "to_amount",
        "to_currency",
        "description",
    ]
    assert rows[1] == [
        "2026-05-01",
        "expense",
        "1234.56",
        "ARS",
        "Cuenta Principal",
        "Comida",
        "Supermercado",
        "",
        "",
        "",
        'Pan "casero" y café',
    ]
    assert rows[2] == [
        "2026-05-02",
        "income",
        "2000.00",
        "ARS",
        "Cuenta Principal",
        "Comida",
        "",
        "",
        "",
        "",
        "Sueldo",
    ]
    assert rows[3] == [
        "2026-05-03",
        "transfer",
        "50.00",
        "ARS",
        "Cuenta Principal",
        "",
        "",
        "Ahorros USD",
        "0.04",
        "USD",
        "Transferencia con, coma",
    ]

    assert rows[1][0] == "2026-05-01"
    assert rows[2][0] == "2026-05-02"
    assert rows[3][0] == "2026-05-03"


@pytest.mark.asyncio
async def test_transactions_export_keeps_blank_subcategory_column_when_missing() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    source_account = await _create_account(user.id, "Cuenta Principal", "ARS")
    category = await _create_category(user.id, "Ingresos", "income")

    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=4500.0,
        currency="ARS",
        transaction_type=TransactionType.income,
        expense_date=date(2026, 5, 4),
        description="Honorarios",
        category_id=category.id,
        subcategory_id=None,
        created_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/expenses/export",
            headers={"Authorization": f"Bearer {token}"},
        )

    rows = _read_csv_rows(response.text)

    assert rows[1][6] == ""
    assert rows[1][5] == "Ingresos"


@pytest.mark.asyncio
async def test_transactions_export_keeps_transfer_category_fields_blank() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    source_account = await _create_account(user.id, "Cuenta Principal", "ARS")
    destination_account = await _create_account(user.id, "Caja de Ahorro", "ARS")

    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=1000.0,
        currency="ARS",
        transaction_type=TransactionType.transfer,
        expense_date=date(2026, 5, 5),
        description="Transferencia interna",
        account_destination_id=destination_account.id,
        to_amount=None,
        created_at=datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/expenses/export",
            headers={"Authorization": f"Bearer {token}"},
        )

    rows = _read_csv_rows(response.text)

    assert rows[1][5] == ""
    assert rows[1][6] == ""
    assert rows[1][7] == "Caja de Ahorro"
    assert rows[1][8] == ""
    assert rows[1][9] == ""


@pytest.mark.asyncio
async def test_transactions_export_orders_same_day_by_created_at() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    source_account = await _create_account(user.id, "Cuenta Principal", "ARS")

    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=300.0,
        currency="ARS",
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 6, 1),
        description="Tercero",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=100.0,
        currency="ARS",
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 6, 1),
        description="Primero",
        created_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
    )
    await _create_transaction(
        user_id=user.id,
        account_id=source_account.id,
        amount=200.0,
        currency="ARS",
        transaction_type=TransactionType.expense,
        expense_date=date(2026, 6, 1),
        description="Segundo",
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/expenses/export",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    rows = _read_csv_rows(response.text)

    assert rows[1][2] == "100.00"
    assert rows[1][10] == "Primero"
    assert rows[2][2] == "200.00"
    assert rows[2][10] == "Segundo"
    assert rows[3][2] == "300.00"
    assert rows[3][10] == "Tercero"
