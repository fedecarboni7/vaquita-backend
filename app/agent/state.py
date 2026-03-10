from typing import Any

from langgraph.graph import MessagesState

from app.agent.schemas import ClassifierOutput


class AgentState(MessagesState):
    classifier_output: ClassifierOutput | None = None
    response_type: str | None = None
    response_payload: dict[str, Any] | None = None
    categories: list[str] = []
    accounts: list[str] = []
