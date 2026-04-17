from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.expenses import TransactionCreate, TransactionUpdate


def test_transaction_create_accepts_account_ids() -> None:
    payload = {
        "amount": 1200.0,
        "description": "Supermercado",
        "type": "expense",
        "account_id": str(uuid4()),
        "expense_date": date(2026, 4, 13).isoformat(),
        "currency": "ARS",
    }

    transaction = TransactionCreate.model_validate(payload)

    assert transaction.account_id is not None


def test_transaction_create_accepts_optional_transfer_conversion_fields() -> None:
    payload = {
        "amount": 100.0,
        "to_amount": 120000.0,
        "description": "Transferencia USD a ARS",
        "type": "transfer",
        "account_id": str(uuid4()),
        "account_destination_id": str(uuid4()),
        "expense_date": date(2026, 4, 16).isoformat(),
        "currency": "USD",
    }

    transaction = TransactionCreate.model_validate(payload)

    assert transaction.to_amount == 120000.0


def test_transaction_create_defaults_affects_balance_to_true() -> None:
    payload = {
        "amount": 1200.0,
        "description": "Supermercado",
        "type": "expense",
        "account_id": str(uuid4()),
        "expense_date": date(2026, 4, 13).isoformat(),
        "currency": "ARS",
    }

    transaction = TransactionCreate.model_validate(payload)

    assert transaction.affects_balance is True


def test_transaction_create_accepts_affects_balance_false() -> None:
    payload = {
        "amount": 1200.0,
        "description": "Ajuste manual",
        "type": "expense",
        "account_id": str(uuid4()),
        "expense_date": date(2026, 4, 13).isoformat(),
        "currency": "ARS",
        "affects_balance": False,
    }

    transaction = TransactionCreate.model_validate(payload)

    assert transaction.affects_balance is False


def test_transaction_create_rejects_legacy_account_string_payload() -> None:
    payload = {
        "amount": 1200.0,
        "description": "Supermercado",
        "type": "expense",
        "account": "Banco",
        "expense_date": date(2026, 4, 13).isoformat(),
        "currency": "ARS",
    }

    with pytest.raises(ValidationError):
        TransactionCreate.model_validate(payload)


def test_transaction_update_rejects_legacy_account_string_field() -> None:
    payload = {
        "account": "Banco",
    }

    with pytest.raises(ValidationError):
        TransactionUpdate.model_validate(payload)


def test_transaction_update_accepts_affects_balance_false() -> None:
    payload = {
        "affects_balance": False,
    }

    transaction = TransactionUpdate.model_validate(payload)

    assert transaction.affects_balance is False
