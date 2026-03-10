from typing import Literal

from pydantic import BaseModel


class RegisterData(BaseModel):
    amount: float
    description: str
    type: Literal["expense", "income", "transfer"]
    account: str
    category: str | None = None
    subcategory: str | None = None
    expense_date: str | None = None
    currency: str = "ARS"
    note: str | None = None


class DirectAnswerData(BaseModel):
    message: str


class ClassifierOutput(BaseModel):
    intent: Literal[
        "register_transaction",
        "direct_answer",
        "clarification_needed",
        "out_of_scope",
    ]
    register_data: RegisterData | None = None
    direct_answer_data: DirectAnswerData | None = None
    clarification_message: str | None = None
