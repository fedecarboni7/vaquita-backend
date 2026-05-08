from typing import Any

from pydantic import BaseModel

from app.models.user_api_key import ApiKeyProvider


class ChatMessageIn(BaseModel):
    role: str
    content: str


class SessionApiKeyPayload(BaseModel):
    provider: ApiKeyProvider
    api_key: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    session_api_key: SessionApiKeyPayload | None = None


class ChatResponse(BaseModel):
    response_type: str
    message: str
    data: dict[str, Any] | None = None
    transcribed_text: str | None = None
    fallback_model_used: bool = False
