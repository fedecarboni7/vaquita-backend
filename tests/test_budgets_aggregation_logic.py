from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.budget import Budget
from app.services.budget_aggregations import allocate_budget_spent, build_budget_aggregation_query


def _budget(category_id, subcategory_id=None, currency="ARS", amount="100.00") -> Budget:
    return Budget(
        id=uuid4(),
        user_id=uuid4(),
        category_id=category_id,
        subcategory_id=subcategory_id,
        currency=currency,
        amount=Decimal(amount),
    )


def test_category_and_subcategory_budgets_count_the_same_transaction_independently() -> None:
    category_id = uuid4()
    covered_subcategory_id = uuid4()
    uncovered_subcategory_id = uuid4()
    category_budget = _budget(category_id)
    subcategory_budget = _budget(category_id, covered_subcategory_id)

    spent = allocate_budget_spent(
        [category_budget, subcategory_budget],
        [
            (category_id, None, "ARS", Decimal("10.00")),
            (category_id, covered_subcategory_id, "ARS", Decimal("20.00")),
            (category_id, uncovered_subcategory_id, "ARS", Decimal("30.00")),
        ],
    )

    assert spent[category_budget.id] == Decimal("60.00")
    assert spent[subcategory_budget.id] == Decimal("20.00")


def test_subcategory_budget_only_counts_its_own_subcategory() -> None:
    category_id = uuid4()
    subcategory_id = uuid4()
    budget = _budget(category_id, subcategory_id)

    spent = allocate_budget_spent(
        [budget],
        [
            (category_id, subcategory_id, "ARS", Decimal("25.00")),
            (category_id, uuid4(), "ARS", Decimal("50.00")),
            (uuid4(), subcategory_id, "ARS", Decimal("75.00")),
        ],
    )

    assert spent[budget.id] == Decimal("25.00")


def test_zero_spend_and_currency_isolation() -> None:
    category_id = uuid4()
    ars_budget = _budget(category_id, currency="ARS")
    usd_budget = _budget(category_id, currency="USD")
    zero_budget = _budget(uuid4())

    spent = allocate_budget_spent(
        [ars_budget, usd_budget, zero_budget],
        [
            (category_id, None, "ARS", Decimal("12.00")),
            (category_id, None, "USD", Decimal("8.00")),
        ],
    )

    assert spent[ars_budget.id] == Decimal("12.00")
    assert spent[usd_budget.id] == Decimal("8.00")
    assert spent[zero_budget.id] == Decimal("0")


def test_query_filters_current_month_expenses_and_balance_effects() -> None:
    query = build_budget_aggregation_query(uuid4(), date(2026, 9, 1), date(2026, 9, 30))
    compiled = str(query)

    assert "transactions.expense_date >=" in compiled
    assert "transactions.expense_date <=" in compiled
    assert "transactions.type" in compiled
    assert "transactions.affects_balance" in compiled
    assert "GROUP BY" in compiled
    assert "transactions.currency" in compiled
