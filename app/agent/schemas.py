from typing import Literal

from pydantic import BaseModel, ConfigDict

CurrencyCode = Literal["ARS", "USD"]


class PendingDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["expense", "income", "transfer"] | None = None
    amount: float | None = None
    to_amount: float | None = None
    description: str | None = None
    account_id: str | None = None
    account_destination_id: str | None = None
    category_id: str | None = None
    subcategory_id: str | None = None
    expense_date: str | None = None
    currency: CurrencyCode | None = None
    installments: int | None = None
    note: str | None = None


class ParseOutput(BaseModel):
    kind: Literal["transaction", "chat"]
    reply: str | None = None
    tx_type: Literal["expense", "income", "transfer"] | None = None
    starts_new_transaction: bool = False
    amount: float | None = None
    to_amount: float | None = None
    description: str | None = None
    account: str | None = None
    account_destination: str | None = None
    category: str | None = None
    subcategory: str | None = None
    date: str | None = None
    currency: CurrencyCode | None = None
    installments: int | None = None
    note: str | None = None
