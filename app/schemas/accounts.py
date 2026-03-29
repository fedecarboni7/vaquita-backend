import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CurrencyCode = Literal["ARS", "USD", "EUR"]
AccountTypeCode = Literal["savings", "checking", "credit_card", "digital_wallet", "cash"]


class AccountCreate(BaseModel):
    name: str
    account_type: AccountTypeCode = "savings"
    currency: CurrencyCode = "ARS"

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
    balance: float
    created_at: datetime
