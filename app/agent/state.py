from typing import Any

from langgraph.graph import MessagesState

from app.agent.schemas import ParseOutput


class AgentState(MessagesState):
    llm: Any = None
    agent_context: Any = None
    pending_draft: dict[str, Any] | None = None
    parse_output: ParseOutput | None = None
    response_type: str | None = None
    response_payload: dict[str, Any] | None = None
    missing_fields: list[str] = []
    inferred_fields: list[str] = []
