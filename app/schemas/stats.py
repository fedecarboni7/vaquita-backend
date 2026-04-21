from pydantic import BaseModel


class StatsSummaryResponse(BaseModel):
    total_income: float
    total_expenses: float
    net_balance: float
    income_delta_pct: float | None
    expenses_delta_pct: float | None
    net_balance_delta_pct: float | None


class StatsMonthlySeriesItem(BaseModel):
    month: str
    total_income: float
    total_expenses: float
    net_balance: float


class StatsCategoryExpenseItem(BaseModel):
    category_name: str
    total: float
    percentage: float


class StatsResponse(BaseModel):
    month: str
    summary: StatsSummaryResponse
    monthly_series: list[StatsMonthlySeriesItem]
    expenses_by_category: list[StatsCategoryExpenseItem]
