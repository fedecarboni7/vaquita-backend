import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

from app.agent.llm import get_llm
from app.agent.nodes import handle_chat, parse, resolve
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_parse(state: AgentState) -> str:
    parse_output = state.get("parse_output")
    if parse_output is None or parse_output.kind == "chat":
        return "handle_chat"
    return "resolve"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("parse", parse)
    graph.add_node("handle_chat", handle_chat)
    graph.add_node("resolve", resolve)

    graph.set_entry_point("parse")
    graph.add_conditional_edges(
        "parse",
        _route_after_parse,
        {
            "handle_chat": "handle_chat",
            "resolve": "resolve",
        },
    )

    graph.add_edge("handle_chat", END)
    graph.add_edge("resolve", END)

    return graph.compile()


_agent = _build_graph()


async def run_agent(
    message: str,
    provider: str,
    api_key: str,
    history: list[dict] | None = None,
    pending_draft: dict[str, Any] | None = None,
    agent_context: Any | None = None,
    llm_override: BaseChatModel | None = None,
) -> dict:
    """Run the agent graph and return response_type, message, and data."""
    history = history[-6:] if history else []
    messages: list[AIMessage | HumanMessage] = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=message))
    llm = llm_override or get_llm(provider=provider, api_key=api_key)

    result = await _agent.ainvoke(
        {
            "messages": messages,
            "llm": llm,
            "pending_draft": pending_draft,
            "agent_context": agent_context,
        }
    )

    last_ai_message = result["messages"][-1]
    outcome = result.get("response_type", "answer")
    parse_output = result.get("parse_output")
    tx_type = None
    if parse_output is not None:
        tx_type = getattr(parse_output, "tx_type", None)
    if result.get("response_payload") is not None:
        tx_type = result["response_payload"].get("type", tx_type)

    logger.info(
        "agent_turn",
        extra={
            "kind": "transaction" if tx_type is not None else getattr(parse_output, "kind", "chat"),
            "tx_type": tx_type,
            "outcome": outcome,
            "missing_fields": result.get("missing_fields") or [],
            "inferred_fields": result.get("inferred_fields") or [],
            "had_pending_draft": pending_draft is not None,
            "starts_new_transaction": getattr(parse_output, "starts_new_transaction", False),
            "provider_model": getattr(llm, "model_name", getattr(llm, "model", provider)),
        },
    )

    return {
        "response_type": outcome,
        "message": last_ai_message.content,
        "data": result.get("response_payload"),
    }
