from typing import Literal

from pydantic import BaseModel, field_validator

CurrencyCode = Literal["ARS", "USD", "EUR"]


class CurrencyNormalizedModel(BaseModel):
    @field_validator("currency", mode="before", check_fields=False)
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class ClassifierOutput(BaseModel):
    intent: Literal["register", "clarification_needed", "direct_answer"]
    subtype: Literal["expense", "income", "transfer"] | None = None
    missing_fields: list[str] | None = None
    clarification_message: str | None = None
    direct_answer_message: str | None = None


class ExpenseExtractorOutput(CurrencyNormalizedModel):
    amount: float
    description: str
    account: str
    category: str | None = None
    subcategory_name: str | None = None
    expense_date: str | None = None
    currency: CurrencyCode = "ARS"
    installments: int | None = None
    note: str | None = None


class IncomeExtractorOutput(CurrencyNormalizedModel):
    amount: float
    description: str
    account: str
    category: str | None = None
    subcategory_name: str | None = None
    expense_date: str | None = None
    currency: CurrencyCode = "ARS"
    note: str | None = None


class TransferExtractorOutput(CurrencyNormalizedModel):
    amount: float
    to_amount: float | None = None
    description: str
    account: str
    account_destination: str
    expense_date: str | None = None
    currency: CurrencyCode = "ARS"
    note: str | None = None
