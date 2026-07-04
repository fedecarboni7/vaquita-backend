import csv
import io
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.account import Account
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.routers.import_csv import REQUIRED_COLUMNS, _staging_store


async def _create_test_user() -> User:
    user = User(
        email=f"import-csv-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Import CSV Test",
    )
    await engine.dispose()
    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _create_account(user_id, name: str, currency: str = "ARS") -> Account:
    account = Account(user_id=user_id, name=name, currency=currency)
    async with async_session_factory() as session:
        session.add(account)
        await session.commit()
        await session.refresh(account)
    return account


async def _create_category(user_id, name: str, category_type: str = "expense") -> Category:
    category = Category(user_id=user_id, name=name, type=category_type)
    async with async_session_factory() as session:
        session.add(category)
        await session.commit()
        await session.refresh(category)
    return category


async def _create_subcategory(user_id, category_id, name: str) -> Subcategory:
    subcategory = Subcategory(user_id=user_id, category_id=category_id, name=name)
    async with async_session_factory() as session:
        session.add(subcategory)
        await session.commit()
        await session.refresh(subcategory)
    return subcategory


def _make_csv(rows: list[list[str]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(REQUIRED_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


@pytest.fixture(autouse=True)
def _clear_staging():
    _staging_store.clear()


# ─── Preview: Happy path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_valid_csv_returns_unique_pairs_and_count() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-05-01", "expense", "100.00", "ARS", "Cuenta Principal", "Comida", "Supermercado", "", "", "", "Pan"],
            ["2026-05-02", "income", "500.00", "ARS", "Cuenta Principal", "Sueldo", "", "", "", "", "Salario"],
            ["2026-05-03", "transfer", "50.00", "ARS", "Cuenta Principal", "", "", "Ahorros", "0.02", "USD", "X"],
            ["2026-05-04", "expense", "30.00", "ARS", "Cuenta Principal", "Comida", "Restaurante", "", "", "", "Cena"],
            [
                "2026-05-05",
                "expense",
                "20.00",
                "ARS",
                "Cuenta Principal",
                "Comida",
                "Supermercado",
                "",
                "",
                "",
                "Leche",
            ],
            ["2026-05-06", "expense", "5.00", "USD", "Ahorros", "Comida", "Supermercado", "", "", "", "US DA"],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["transaction_count"] == 6
    assert len(data["unique_pairs"]) == 3

    pairs = {(p["category_name"], p["subcategory_name"]) for p in data["unique_pairs"]}
    assert ("Comida", "Supermercado") in pairs
    assert ("Comida", "Restaurante") in pairs
    assert ("Sueldo", None) in pairs
    assert isinstance(data["staging_token"], str)
    assert len(data["staging_token"]) > 0


@pytest.mark.asyncio
async def test_preview_requires_auth() -> None:
    csv_content = _make_csv([["2026-05-01", "expense", "100.00", "ARS", "Cuenta", "Cat", "Sub", "", "", "", "Desc"]])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/import/preview", files={"file": ("test.csv", csv_content, "text/csv")})
    assert response.status_code == 401


# ─── Preview: Validation errors ────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_missing_column_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "type", "amount", "currency", "account_name"])
    writer.writerow(["2026-01-01", "expense", "10.00", "ARS", "Account"])
    csv_content = output.getvalue()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_preview_unknown_transaction_type_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv([["2026-01-01", "gasto", "10.00", "ARS", "Account", "Cat", "", "", "", "", "Desc"]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "tipo de transacción" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_invalid_date_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv([["not-a-date", "expense", "10.00", "ARS", "Account", "Cat", "", "", "", "", "Desc"]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "fecha" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_invalid_amount_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv([["2026-01-01", "expense", "abc", "ARS", "Account", "Cat", "", "", "", "", "Desc"]])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "monto" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_transfer_unknown_destination_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "transfer", "100.00", "ARS", "Source", "", "", "NonExistent", "0.01", "USD", "X"],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "cuenta destino" in response.json()["detail"].lower()
    assert "nonexistent" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_transfer_without_destination_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "transfer", "100.00", "ARS", "Source", "", "", "", "", "", "X"],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "cuenta destino" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_mixed_currency_for_same_account_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "100.00", "ARS", "Caja", "Cat", "", "", "", "", "X"],
            ["2026-01-02", "expense", "50.00", "USD", "Caja", "Cat2", "", "", "", "", "Y"],
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400
    assert "monedas mixtas" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_empty_file_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("empty.csv", "", "text/csv")},
        )

    assert response.status_code == 400
    assert "vací" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_preview_csv_with_only_headers_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(REQUIRED_COLUMNS)
    csv_content = output.getvalue()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_preview_non_csv_extension_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("data.txt", "some,data", "text/plain")},
        )

    assert response.status_code == 400
    assert ".csv" in response.json()["detail"].lower()


# ─── Confirm: Happy path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_creates_accounts_never_matches_existing() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    # Pre-create an account with the same name — import should still create a new one
    await _create_account(user.id, "Cuenta Principal", "ARS")

    csv_content = _make_csv(
        [["2026-01-01", "expense", "100.00", "ARS", "Cuenta Principal", "Comida", "", "", "", "", "Desc"]]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Comida",
                "subcategory_name": None,
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    data = confirm_resp.json()
    assert data["created_transactions"] == 1
    assert "Cuenta Principal" in data["created_accounts"]

    # Verify new account was created (distinct from existing)
    async with async_session_factory() as session:
        accounts = (await session.execute(select(Account).where(Account.user_id == user.id))).scalars().all()
        assert len(accounts) == 2
        assert accounts[0].id != accounts[1].id


@pytest.mark.asyncio
async def test_confirm_maps_to_existing_category_and_subcategory() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    existing_cat = await _create_category(user.id, "Comida", "expense")
    existing_sub = await _create_subcategory(user.id, existing_cat.id, "Supermercado")

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "100.00", "ARS", "Caja", "Comida", "Supermercado", "", "", "", "Desc"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Comida",
                "subcategory_name": "Supermercado",
                "existing_category_id": str(existing_cat.id),
                "existing_subcategory_id": str(existing_sub.id),
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    assert confirm_resp.json()["created_transactions"] == 1

    async with async_session_factory() as session:
        txn = (await session.execute(select(Transaction).where(Transaction.user_id == user.id))).scalar_one()
        assert txn.category_id == existing_cat.id
        assert txn.subcategory_id == existing_sub.id


@pytest.mark.asyncio
async def test_confirm_creates_new_category_and_subcategory() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "100.00", "ARS", "Caja", "NuevaCat", "NuevaSub", "", "", "", "Desc"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "NuevaCat",
                "subcategory_name": "NuevaSub",
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    data = confirm_resp.json()
    assert data["created_transactions"] == 1
    assert "NuevaCat" in data["created_categories"]
    assert "NuevaSub" in data["created_subcategories"]

    async with async_session_factory() as session:
        cat = (
            await session.execute(select(Category).where(Category.name == "NuevaCat", Category.user_id == user.id))
        ).scalar_one()
        sub = (
            await session.execute(
                select(Subcategory).where(Subcategory.name == "NuevaSub", Subcategory.user_id == user.id)
            )
        ).scalar_one()
        assert sub.category_id == cat.id


@pytest.mark.asyncio
async def test_confirm_creates_subcategory_under_existing_category() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    existing_cat = await _create_category(user.id, "Transporte", "expense")

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "50.00", "ARS", "Caja", "Transporte", "Taxi", "", "", "", "Viaje"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Transporte",
                "subcategory_name": "Taxi",
                "existing_category_id": str(existing_cat.id),
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    async with async_session_factory() as session:
        sub = (
            await session.execute(
                select(Subcategory).where(
                    Subcategory.name == "Taxi",
                    Subcategory.user_id == user.id,
                )
            )
        ).scalar_one()
        assert sub.category_id == existing_cat.id


@pytest.mark.asyncio
async def test_confirm_persists_transfer_with_cross_currency() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "transfer", "1000.00", "ARS", "Caja Ahorro", "", "", "Caja USD", "1.00", "USD", "Conv"],
            ["2026-01-02", "expense", "10.00", "USD", "Caja USD", "Comisiones", "", "", "", "", "Fee"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Comisiones",
                "subcategory_name": None,
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    data = confirm_resp.json()
    assert data["created_transactions"] == 2
    assert "Caja Ahorro" in data["created_accounts"]
    assert "Caja USD" in data["created_accounts"]
    assert "Comisiones" in data["created_categories"]

    async with async_session_factory() as session:
        txns = (
            (
                await session.execute(
                    select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.expense_date)
                )
            )
            .scalars()
            .all()
        )
        assert len(txns) == 2
        txn = txns[0]
        assert txn.type == TransactionType.transfer
        assert float(txn.amount) == 1000.00
        assert txn.currency == "ARS"
        assert float(txn.to_amount) == 1.00

        src_account = await session.get(Account, txn.account_id)
        dest_account = await session.get(Account, txn.account_destination_id)
        assert src_account is not None
        assert dest_account is not None
        assert src_account.name == "Caja Ahorro"
        assert src_account.currency == "ARS"
        assert dest_account.name == "Caja USD"
        assert dest_account.currency == "USD"


@pytest.mark.asyncio
async def test_confirm_same_currency_transfer() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "transfer", "500.00", "ARS", "Caja A", "", "", "Caja B", "", "", "Movimiento"],
            ["2026-01-02", "expense", "25.00", "ARS", "Caja B", "Servicios", "", "", "", "", "Pago"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Servicios",
                "subcategory_name": None,
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    assert confirm_resp.json()["created_transactions"] == 2

    async with async_session_factory() as session:
        txns = (
            (
                await session.execute(
                    select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.expense_date)
                )
            )
            .scalars()
            .all()
        )
        assert len(txns) == 2
        txn = txns[0]
        assert txn.type == TransactionType.transfer
        assert txn.to_amount is None

        dest_account = await session.get(Account, txn.account_destination_id)
        assert dest_account is not None
        assert dest_account.currency == "ARS"


# ─── Confirm: Validation errors ────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_invalid_staging_token_returns_400() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    confirm_body = {"staging_token": "nonexistent", "mapping": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert response.status_code == 400
    assert "token" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_requires_auth() -> None:
    confirm_body = {"staging_token": "x", "mapping": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/import/confirm", json=confirm_body)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_confirm_staging_token_invalidated_after_use() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv([["2026-01-01", "expense", "100.00", "ARS", "Caja", "Cat", "", "", "", "", "Desc"]])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Cat",
                "subcategory_name": None,
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/import/confirm", headers={"Authorization": f"Bearer {token}"}, json=confirm_body)
        assert first.status_code == 201

        second = await client.post("/import/confirm", headers={"Authorization": f"Bearer {token}"}, json=confirm_body)
        assert second.status_code == 400
        assert "token" in second.json()["detail"].lower()


# ─── Confirm: All-or-nothing rollback ──────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_rolls_back_on_failure() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "100.00", "ARS", "AccountA", "Cat", "", "", "", "", "X"],
            ["2026-01-02", "income", "200.00", "ARS", "AccountB", "Cat", "", "", "", "", "Y"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    # Provide a non-existent category ID to trigger a failure
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Cat",
                "subcategory_name": None,
                "existing_category_id": fake_uuid,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert response.status_code == 400

    # Verify no accounts or transactions were created
    async with async_session_factory() as session:
        accounts = (await session.execute(select(Account).where(Account.user_id == user.id))).scalars().all()
        transactions = (
            (await session.execute(select(Transaction).where(Transaction.user_id == user.id))).scalars().all()
        )
        assert len(accounts) == 0
        assert len(transactions) == 0


# ─── Confirm: Multiple category mappings ───────────────────────────────


@pytest.mark.asyncio
async def test_confirm_multiple_categories_mapped_correctly() -> None:
    user = await _create_test_user()
    token = create_access_token(user.id)

    csv_content = _make_csv(
        [
            ["2026-01-01", "expense", "100.00", "ARS", "Caja", "Comida", "Super", "", "", "", "Pan"],
            ["2026-01-02", "income", "500.00", "ARS", "Caja", "Sueldo", "", "", "", "", "Salary"],
            ["2026-01-03", "expense", "30.00", "ARS", "Caja", "Comida", "Super", "", "", "", "Leche"],
            ["2026-01-04", "expense", "20.00", "ARS", "Caja", "Comida", "Resto", "", "", "", "Cena"],
        ]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_resp = await client.post(
            "/import/preview",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
    staging_token = preview_resp.json()["staging_token"]

    confirm_body = {
        "staging_token": staging_token,
        "mapping": [
            {
                "category_name": "Comida",
                "subcategory_name": "Super",
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
            {
                "category_name": "Comida",
                "subcategory_name": "Resto",
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
            {
                "category_name": "Sueldo",
                "subcategory_name": None,
                "existing_category_id": None,
                "existing_subcategory_id": None,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        confirm_resp = await client.post(
            "/import/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json=confirm_body,
        )

    assert confirm_resp.status_code == 201
    data = confirm_resp.json()
    assert data["created_transactions"] == 4
    assert len(data["created_categories"]) == 2  # Comida and Sueldo
    assert len(data["created_subcategories"]) == 2  # Super and Resto
