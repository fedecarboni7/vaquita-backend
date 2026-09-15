from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import UUID
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.transaction import Transaction, TransactionType


def build_budget_aggregation_query(user_id: UUID, month_start: date, month_end: date):
    total = func.sum(Transaction.amount)
    return (
        select(
            Transaction.category_id,
            Transaction.subcategory_id,
            Transaction.currency,
            total.label("spent"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.expense_date >= month_start,
            Transaction.expense_date <= month_end,
            Transaction.type == TransactionType.expense,
            Transaction.affects_balance.is_(True),
        )
        .group_by(Transaction.category_id, Transaction.subcategory_id, Transaction.currency)
    )


def allocate_budget_spent(
    budgets: list[Budget],
    rows: Iterable[tuple[UUID | None, UUID | None, str, Decimal]],
) -> dict[UUID, Decimal]:
    spent_by_budget: dict[UUID, Decimal] = {budget.id: Decimal("0") for budget in budgets}
    for category_id, subcategory_id, currency, spent in rows:
        amount = Decimal(str(spent))
        for budget in budgets:
            if budget.currency != currency or budget.category_id != category_id:
                continue
            if budget.subcategory_id is not None and budget.subcategory_id != subcategory_id:
                continue
            spent_by_budget[budget.id] += amount
    return spent_by_budget


async def calculate_budget_spent(
    session: AsyncSession,
    user_id: UUID,
    budgets: list[Budget],
) -> dict[UUID, Decimal]:
    if not budgets:
        return {}

    today = date.today()
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    query = build_budget_aggregation_query(user_id, month_start, month_end)
    result = await session.execute(query)
    rows = [(row.category_id, row.subcategory_id, row.currency, row.spent) for row in result.all()]
    return allocate_budget_spent(budgets, rows)
