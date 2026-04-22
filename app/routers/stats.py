from calendar import monthrange
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.stats import (
    StatsCategoryExpenseItem,
    StatsMonthlySeriesItem,
    StatsResponse,
    StatsSummaryResponse,
)

router = APIRouter(prefix="/stats", tags=["stats"])


def _parse_month(month: str) -> date:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="month must use YYYY-MM format",
        ) from exc

    return date(parsed.year, parsed.month, 1)


def _month_bounds(month_start: date) -> tuple[date, date]:
    month_end = date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )
    return month_start, month_end


def _shift_month(month_start: date, delta: int) -> date:
    month_index = (month_start.year * 12 + (month_start.month - 1)) + delta
    target_year = month_index // 12
    target_month = (month_index % 12) + 1
    return date(target_year, target_month, 1)


def _month_key(month_start: date) -> str:
    return month_start.strftime("%Y-%m")


def _compute_delta_pct(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None

    delta = ((current - previous) / abs(previous)) * 100
    return round(delta, 1)


def _apply_stats_currency_filter(base_query, *, currency: Literal["ARS", "USD"]):
    return base_query.join(Account, Account.id == Transaction.account_id).where(Account.currency == currency)


async def _fetch_month_totals(
    session: AsyncSession,
    *,
    user_id,
    month_start: date,
    month_end: date,
    currency: Literal["ARS", "USD"],
) -> tuple[float, float, int]:
    income_expr = case(
        (Transaction.type == TransactionType.income, Transaction.amount),
        else_=0,
    )
    expense_expr = case(
        (Transaction.type == TransactionType.expense, Transaction.amount),
        else_=0,
    )

    query = select(
        func.coalesce(func.sum(income_expr), 0).label("total_income"),
        func.coalesce(func.sum(expense_expr), 0).label("total_expenses"),
        func.count(Transaction.id).label("transaction_count"),
    ).where(
        Transaction.user_id == user_id,
        Transaction.expense_date >= month_start,
        Transaction.expense_date <= month_end,
        Transaction.affects_balance.is_(True),
        Transaction.type.in_([TransactionType.income, TransactionType.expense]),
    )
    query = _apply_stats_currency_filter(query, currency=currency)

    result = await session.execute(query)
    row = result.one()
    return float(row.total_income), float(row.total_expenses), int(row.transaction_count)


async def _fetch_monthly_series(
    session: AsyncSession,
    *,
    user_id,
    from_month_start: date,
    to_month_end: date,
    requested_month_start: date,
    currency: Literal["ARS", "USD"],
) -> list[StatsMonthlySeriesItem]:
    income_expr = case(
        (Transaction.type == TransactionType.income, Transaction.amount),
        else_=0,
    )
    expense_expr = case(
        (Transaction.type == TransactionType.expense, Transaction.amount),
        else_=0,
    )
    month_bucket = func.date_trunc(literal("month"), Transaction.expense_date)

    query = (
        select(
            month_bucket.label("month_bucket"),
            func.coalesce(func.sum(income_expr), 0).label("total_income"),
            func.coalesce(func.sum(expense_expr), 0).label("total_expenses"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.expense_date >= from_month_start,
            Transaction.expense_date <= to_month_end,
            Transaction.affects_balance.is_(True),
            Transaction.type.in_([TransactionType.income, TransactionType.expense]),
        )
        .group_by(month_bucket)
        .order_by(month_bucket)
    )
    query = _apply_stats_currency_filter(query, currency=currency)

    result = await session.execute(query)

    values_by_month: dict[str, tuple[float, float]] = {}
    for row in result.all():
        bucket_date = row.month_bucket.date()
        values_by_month[_month_key(bucket_date)] = (
            float(row.total_income),
            float(row.total_expenses),
        )

    series: list[StatsMonthlySeriesItem] = []
    for offset in range(-5, 1):
        month_start = _shift_month(requested_month_start, offset)
        month_str = _month_key(month_start)
        total_income, total_expenses = values_by_month.get(month_str, (0.0, 0.0))
        series.append(
            StatsMonthlySeriesItem(
                month=month_str,
                total_income=total_income,
                total_expenses=total_expenses,
                net_balance=total_income - total_expenses,
            )
        )

    return series


async def _fetch_expenses_by_category(
    session: AsyncSession,
    *,
    user_id,
    month_start: date,
    month_end: date,
    currency: Literal["ARS", "USD"],
) -> list[StatsCategoryExpenseItem]:
    category_label = func.coalesce(Category.name, literal("Sin categoría"))
    category_total = func.sum(Transaction.amount)
    total_expenses_window = func.sum(func.sum(Transaction.amount)).over()
    percentage_expr = func.round(
        case(
            (total_expenses_window == 0, 0),
            else_=(category_total * 100.0 / total_expenses_window),
        ),
        1,
    )

    query = (
        select(
            category_label.label("category_name"),
            category_total.label("total"),
            percentage_expr.label("percentage"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.expense_date >= month_start,
            Transaction.expense_date <= month_end,
            Transaction.affects_balance.is_(True),
            Transaction.type == TransactionType.expense,
        )
        .group_by(category_label)
        .order_by(category_total.desc())
    )
    query = _apply_stats_currency_filter(query, currency=currency)

    result = await session.execute(query)

    return [
        StatsCategoryExpenseItem(
            category_name=str(row.category_name),
            total=float(row.total),
            percentage=float(row.percentage),
        )
        for row in result.all()
    ]


@router.get("", response_model=StatsResponse)
async def get_stats(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    currency: Literal["ARS", "USD"] = Query("ARS"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    requested_month_start = _parse_month(month)
    requested_month_start, requested_month_end = _month_bounds(requested_month_start)

    previous_month_start = _shift_month(requested_month_start, -1)
    previous_month_start, previous_month_end = _month_bounds(previous_month_start)

    total_income, total_expenses, _ = await _fetch_month_totals(
        session,
        user_id=current_user.id,
        month_start=requested_month_start,
        month_end=requested_month_end,
        currency=currency,
    )
    prev_income, prev_expenses, prev_count = await _fetch_month_totals(
        session,
        user_id=current_user.id,
        month_start=previous_month_start,
        month_end=previous_month_end,
        currency=currency,
    )

    net_balance = total_income - total_expenses
    prev_net_balance = prev_income - prev_expenses if prev_count > 0 else None

    monthly_series = await _fetch_monthly_series(
        session,
        user_id=current_user.id,
        from_month_start=_shift_month(requested_month_start, -5),
        to_month_end=requested_month_end,
        requested_month_start=requested_month_start,
        currency=currency,
    )

    expenses_by_category = await _fetch_expenses_by_category(
        session,
        user_id=current_user.id,
        month_start=requested_month_start,
        month_end=requested_month_end,
        currency=currency,
    )

    summary = StatsSummaryResponse(
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=net_balance,
        income_delta_pct=_compute_delta_pct(total_income, prev_income if prev_count > 0 else None),
        expenses_delta_pct=_compute_delta_pct(total_expenses, prev_expenses if prev_count > 0 else None),
        net_balance_delta_pct=_compute_delta_pct(net_balance, prev_net_balance),
    )

    return StatsResponse(
        month=_month_key(requested_month_start),
        summary=summary,
        monthly_series=monthly_series,
        expenses_by_category=expenses_by_category,
    )
