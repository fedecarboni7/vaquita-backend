import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CurrencyCode = Literal["ARS", "USD"]


class BudgetCreate(BaseModel):
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    currency: CurrencyCode = "ARS"

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: CurrencyCode | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.upper()
        return value


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None
    amount: Decimal
    currency: CurrencyCode
    created_at: datetime
    updated_at: datetime
    spent: Decimal
    remaining: Decimal
    percentage: float
