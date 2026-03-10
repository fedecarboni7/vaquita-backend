from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.agent.nodes import classify, handle_direct, handle_register
from app.agent.state import AgentState


def _route_by_intent(state: AgentState) -> str:
    intent = state["classifier_output"].intent
    if intent == "register_transaction":
        return "handle_register"
    return "handle_direct"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify", classify)
    graph.add_node("handle_register", handle_register)
    graph.add_node("handle_direct", handle_direct)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", _route_by_intent)
    graph.add_edge("handle_register", END)
    graph.add_edge("handle_direct", END)

    return graph.compile()


_agent = _build_graph()


async def run_agent(
    message: str,
    history: list[dict] | None = None,
    categories: list[str] | None = None,
    accounts: list[str] | None = None,
) -> dict:
    """Run the classifier agent and return response_type, message, and data.

    Args:
        message: The current user message.
        history: Optional list of previous messages (dicts with role/content).
        categories: Distinct categories from the user's transactions.
        accounts: Distinct accounts from the user's transactions.
    """
    messages = []
    if history:
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                from langchain_core.messages import AIMessage

                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=message))

    result = await _agent.ainvoke(
        {
            "messages": messages,
            "categories": categories or [],
            "accounts": accounts or [],
        }
    )

    last_ai_message = result["messages"][-1]

    return {
        "response_type": result.get("response_type", "answer"),
        "message": last_ai_message.content,
        "data": result.get("response_payload"),
    }
