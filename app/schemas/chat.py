from typing import Any

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]


class ChatResponse(BaseModel):
    response_type: str
    message: str
    data: dict[str, Any] | None = None
    transcribed_text: str | None = None
