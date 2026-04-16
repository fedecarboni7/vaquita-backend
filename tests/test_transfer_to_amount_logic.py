from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.expenses import _normalize_transfer_to_amount


def test_normalize_transfer_to_amount_cross_currency() -> None:
    to_amount = _normalize_transfer_to_amount(120000)

    assert to_amount == Decimal("120000.00")


def test_normalize_transfer_to_amount_same_currency_fallback() -> None:
    to_amount = _normalize_transfer_to_amount(None)

    assert to_amount is None


def test_normalize_transfer_to_amount_rejects_non_positive_to_amount() -> None:
    with pytest.raises(HTTPException) as exc:
        _normalize_transfer_to_amount(0)

    assert exc.value.status_code == 422
    assert exc.value.detail == "to_amount must be greater than 0"
