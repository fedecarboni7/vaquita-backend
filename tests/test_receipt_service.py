from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import async_session_factory, engine
from app.main import app
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services import r2

VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


class _FakeR2Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def put_object(self, **kwargs) -> None:
        self.calls.append(kwargs)

    def generate_presigned_url(self, *args, **kwargs) -> str:
        return "http://fake-signed-url"


async def _create_test_user() -> User:
    user = User(
        email=f"receipt-{uuid4()}@example.com",
        google_id=str(uuid4()),
        display_name="Receipt Test",
    )

    await engine.dispose()

    async with async_session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def _create_test_account(user_id: UUID) -> Account:
    account = Account(
        user_id=user_id,
        name="Cuenta prueba",
    )

    async with async_session_factory() as session:
        session.add(account)
        await session.commit()
        await session.refresh(account)

    return account


async def _create_test_transaction(user_id: UUID, account_id: UUID) -> Transaction:
    transaction = Transaction(
        id=uuid4(),
        user_id=user_id,
        amount=1200.0,
        currency="ARS",
        type=TransactionType.expense,
        account_id=account_id,
        description="Supermercado",
        expense_date=date(2026, 5, 1),
        affects_balance=True,
    )

    async with async_session_factory() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

    return transaction


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "extension"),
    [
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
    ],
)
async def test_upload_receipt_generates_expected_key(
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    extension: str,
) -> None:
    fake_client = _FakeR2Client()
    monkeypatch.setattr(r2, "_r2_client", fake_client)

    object_key = await r2.upload_receipt(
        file_bytes=b"data",
        content_type=content_type,
        user_id="user-123",
        transaction_id="tx-456",
    )

    assert object_key == f"receipts/user-123/tx-456.{extension}"
    assert fake_client.calls
    assert fake_client.calls[0]["Key"] == object_key


@pytest.mark.asyncio
async def test_upload_receipt_rejects_invalid_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    user = await _create_test_user()
    account = await _create_test_account(user.id)
    transaction = await _create_test_transaction(user.id, account.id)
    token = create_access_token(user.id)

    fake_kind = MagicMock()
    fake_kind.mime = "application/octet-stream"
    monkeypatch.setattr("app.routers.expenses.filetype.guess", lambda _: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/expenses/{transaction.id}/receipt",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("receipt.txt", b"not-an-image", "text/plain")},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_receipt_rejects_invalid_type(monkeypatch: pytest.MonkeyPatch) -> None:
    user = await _create_test_user()
    account = await _create_test_account(user.id)
    transaction = await _create_test_transaction(user.id, account.id)
    token = create_access_token(user.id)

    fake_kind = MagicMock()
    fake_kind.mime = "application/pdf"
    monkeypatch.setattr("app.routers.expenses.filetype.guess", lambda _: fake_kind)

    with patch("app.routers.expenses.check_and_increment_upload_usage", AsyncMock()):
        with patch.object(r2, "upload_receipt", return_value="key"):
            with patch.object(r2, "get_receipt_signed_url", return_value="http://signed"):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        f"/expenses/{transaction.id}/receipt",
                        headers={"Authorization": f"Bearer {token}"},
                        files={"file": ("receipt.txt", b"fake-pdf", "application/pdf")},
                    )

    assert response.status_code == 422
    assert "no permitido" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_receipt_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    user = await _create_test_user()
    account = await _create_test_account(user.id)
    transaction = await _create_test_transaction(user.id, account.id)
    token = create_access_token(user.id)

    large_content = b"\x00" * (2 * 1024 * 1024)

    fake_kind = MagicMock()
    fake_kind.mime = "image/jpeg"
    monkeypatch.setattr("app.routers.expenses.filetype.guess", lambda _: fake_kind)

    with patch.object(r2, "upload_receipt", return_value="key"):
        with patch.object(r2, "get_receipt_signed_url", return_value="http://signed"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    f"/expenses/{transaction.id}/receipt",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("receipt.jpg", large_content, "image/jpeg")},
                )

    assert response.status_code == 413
    assert "1MB" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_receipt_valid_type(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeR2Client()
    monkeypatch.setattr(r2, "_r2_client", fake_client)

    fake_kind = MagicMock()
    fake_kind.mime = "image/jpeg"
    monkeypatch.setattr("app.routers.expenses.filetype.guess", lambda _: fake_kind)

    user = await _create_test_user()
    account = await _create_test_account(user.id)
    transaction = await _create_test_transaction(user.id, account.id)
    token = create_access_token(user.id)

    with patch.object(r2, "get_receipt_signed_url", new=AsyncMock(return_value="http://signed")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/expenses/{transaction.id}/receipt",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
            )

    assert response.status_code == 200
    assert "receipt_url" in response.json()
    assert fake_client.calls
