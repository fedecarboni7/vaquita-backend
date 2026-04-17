import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CurrencyCode = Literal["ARS", "USD", "EUR"]
AccountTypeCode = Literal["savings", "checking", "credit_card", "digital_wallet", "cash"]


class AccountCreate(BaseModel):
    name: str
    account_type: AccountTypeCode = "savings"
    currency: CurrencyCode = "ARS"
    include_in_total: bool | None = None
    billing_period_start: date | None = None
    billing_period_end: date | None = None
    payment_due_date: date | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class AccountUpdate(BaseModel):
    name: str
    account_type: AccountTypeCode
    currency: CurrencyCode
    include_in_total: bool | None = None
    billing_period_start: date | None = None
    billing_period_end: date | None = None
    payment_due_date: date | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    account_type: AccountTypeCode
    currency: CurrencyCode
    include_in_total: bool
    billing_period_start: date | None
    billing_period_end: date | None
    payment_due_date: date | None
    closed_period_balance: float | None
    balance: float
    created_at: datetime


class AccountAdjustRequest(BaseModel):
    balance: float
    affects_balance: bool = True


class AccountAdjustResponse(BaseModel):
    applied: bool
    delta: float
