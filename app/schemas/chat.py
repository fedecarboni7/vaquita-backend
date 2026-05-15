import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    thread_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    response_type: str
    message: str
    data: dict[str, Any] | None = None
    transcribed_text: str | None = None
    fallback_model_used: bool = False
    thread_id: uuid.UUID | None = None


class ChatThreadSummary(BaseModel):
    thread_id: uuid.UUID
    started_at: datetime
    interaction_count: int
    transactions_created: int


class ChatThreadsResponse(BaseModel):
    threads: list[ChatThreadSummary]


class ChatThreadInteraction(BaseModel):
    id: uuid.UUID
    user_message: str
    agent_reply: str
    created_at: datetime


class ChatThreadDetailResponse(BaseModel):
    thread_id: uuid.UUID
    interactions: list[ChatThreadInteraction]
