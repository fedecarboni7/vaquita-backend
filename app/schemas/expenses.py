import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    amount: float
    description: str
    type: Literal["expense", "income", "transfer"]
    account: str
    expense_date: date
    category: str | None = None
    subcategory_id: uuid.UUID | None = None
    currency: str = "ARS"
    note: str | None = None
    installments: int | None = None
    account_destination: str | None = None


class TransactionUpdate(BaseModel):
    amount: float | None = None
    description: str | None = None
    type: Literal["expense", "income", "transfer"] | None = None
    account: str | None = None
    expense_date: date | None = None
    category: str | None = None
    subcategory_id: uuid.UUID | None = None
    currency: str | None = None
    note: str | None = None
    installments: int | None = None
    account_destination: str | None = None


class PaginatedTransactionsResponse(BaseModel):
    items: list["TransactionResponse"]
    total: int
    has_more: bool


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: float
    description: str
    type: str
    account: str
    expense_date: date
    category: str | None = None
    subcategory_id: uuid.UUID | None = None
    subcategory_name: str | None = None
    currency: str
    note: str | None = None
    installments: int | None = None
    account_destination: str | None = None
    created_at: datetime
    updated_at: datetime
