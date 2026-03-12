from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    classify,
    extract_expense,
    extract_income,
    extract_transfer,
    handle_clarification,
    handle_direct_answer,
    validate,
)
from app.agent.state import AgentState


def _route_after_classify(state: AgentState) -> str:
    output = state["classifier_output"]
    intent = output.intent

    if intent == "clarification_needed":
        return "handle_clarification"
    if intent == "direct_answer":
        return "handle_direct_answer"

    # intent == "register" → route by subtype
    subtype = output.subtype
    return f"extract_{subtype}"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify", classify)
    graph.add_node("handle_clarification", handle_clarification)
    graph.add_node("handle_direct_answer", handle_direct_answer)
    graph.add_node("extract_expense", extract_expense)
    graph.add_node("extract_income", extract_income)
    graph.add_node("extract_transfer", extract_transfer)
    graph.add_node("validate", validate)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "handle_clarification": "handle_clarification",
            "handle_direct_answer": "handle_direct_answer",
            "extract_expense": "extract_expense",
            "extract_income": "extract_income",
            "extract_transfer": "extract_transfer",
        },
    )

    graph.add_edge("handle_clarification", END)
    graph.add_edge("handle_direct_answer", END)
    graph.add_edge("extract_expense", "validate")
    graph.add_edge("extract_income", "validate")
    graph.add_edge("extract_transfer", "validate")
    graph.add_edge("validate", END)

    return graph.compile()


_agent = _build_graph()


async def run_agent(
    message: str,
    history: list[dict] | None = None,
    expense_categories: list[str] | None = None,
    income_categories: list[str] | None = None,
    accounts: list[str] | None = None,
) -> dict:
    """Run the agent graph and return response_type, message, and data.

    Args:
        message: The current user message.
        history: Optional list of previous messages (dicts with role/content).
        expense_categories: Expense category names for the user.
        income_categories: Income category names for the user.
        accounts: Account names for the user.
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
            "expense_categories": expense_categories or [],
            "income_categories": income_categories or [],
            "accounts": accounts or [],
        }
    )

    last_ai_message = result["messages"][-1]

    return {
        "response_type": result.get("response_type", "answer"),
        "message": last_ai_message.content,
        "data": result.get("response_payload"),
    }
