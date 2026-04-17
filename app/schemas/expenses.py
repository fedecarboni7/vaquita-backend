import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CurrencyCode = Literal["ARS", "USD", "EUR"]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float
    description: str
    type: Literal["expense", "income", "transfer"]
    account_id: uuid.UUID
    expense_date: date
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    currency: CurrencyCode = "ARS"
    note: str | None = None
    installments: int | None = None
    account_destination_id: uuid.UUID | None = None
    to_amount: float | None = None
    affects_balance: bool = True

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float | None = None
    description: str | None = None
    type: Literal["expense", "income", "transfer"] | None = None
    account_id: uuid.UUID | None = None
    expense_date: date | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    currency: CurrencyCode | None = None
    note: str | None = None
    installments: int | None = None
    account_destination_id: uuid.UUID | None = None
    to_amount: float | None = None
    affects_balance: bool | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.upper()
        return value


class PaginatedTransactionsResponse(BaseModel):
    items: list["TransactionResponse"]
    total: int
    has_more: bool


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: float
    description: str | None
    type: str
    account_id: uuid.UUID | None = None
    account: str | None
    expense_date: date
    category_id: uuid.UUID | None = None
    category_name: str | None = None
    subcategory_id: uuid.UUID | None = None
    subcategory_name: str | None = None
    currency: CurrencyCode
    note: str | None = None
    installments: int | None = None
    account_destination_id: uuid.UUID | None = None
    account_destination: str | None = None
    account_destination_currency: CurrencyCode | None = None
    to_amount: float | None = None
    affects_balance: bool
    created_at: datetime
    updated_at: datetime
