from datetime import date

import pytest
from fastapi import HTTPException

from app.routers.stats import (
    _compute_delta_pct,
    _month_bounds,
    _month_key,
    _parse_month,
    _shift_month,
)


def test_parse_month_accepts_valid_input() -> None:
    assert _parse_month("2026-04") == date(2026, 4, 1)


def test_parse_month_rejects_invalid_input() -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_month("2026-13")

    assert exc.value.status_code == 422
    assert exc.value.detail == "month must use YYYY-MM format"


def test_month_bounds_for_february_leap_year() -> None:
    month_start, month_end = _month_bounds(date(2024, 2, 1))

    assert month_start == date(2024, 2, 1)
    assert month_end == date(2024, 2, 29)


def test_shift_month_crosses_year_boundaries() -> None:
    assert _shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert _shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_month_key_uses_yyyy_mm_format() -> None:
    assert _month_key(date(2026, 4, 1)) == "2026-04"


def test_compute_delta_pct_matches_formula() -> None:
    assert _compute_delta_pct(120.0, 100.0) == 20.0
    assert _compute_delta_pct(80.0, 100.0) == -20.0


def test_compute_delta_pct_returns_none_when_previous_is_zero_or_missing() -> None:
    assert _compute_delta_pct(100.0, 0.0) is None
    assert _compute_delta_pct(100.0, None) is None
