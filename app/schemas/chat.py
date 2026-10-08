from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


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
    currency: Literal["ARS", "USD"] | None = None
    installments: int | None = None
    note: str | None = None


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    pending_draft: PendingDraft | None = None


class ChatResponse(BaseModel):
    response_type: str
    message: str
    data: dict[str, Any] | None = None
    transcribed_text: str | None = None
    fallback_model_used: bool = False
