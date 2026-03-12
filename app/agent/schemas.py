from typing import Literal

from pydantic import BaseModel


class ClassifierOutput(BaseModel):
    intent: Literal["register", "clarification_needed", "direct_answer"]
    subtype: Literal["expense", "income", "transfer"] | None = None
    missing_fields: list[str] | None = None
    clarification_message: str | None = None
    direct_answer_message: str | None = None


class ExpenseExtractorOutput(BaseModel):
    amount: float
    description: str
    account: str
    category: str | None = None
    subcategory: str | None = None
    expense_date: str | None = None
    currency: str = "ARS"
    installments: int | None = None
    note: str | None = None


class IncomeExtractorOutput(BaseModel):
    amount: float
    description: str
    account: str
    category: str | None = None
    subcategory: str | None = None
    expense_date: str | None = None
    currency: str = "ARS"
    note: str | None = None


class TransferExtractorOutput(BaseModel):
    amount: float
    description: str
    account: str
    account_destination: str
    expense_date: str | None = None
    currency: str = "ARS"
    note: str | None = None
