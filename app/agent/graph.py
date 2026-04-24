from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.agent.llm import get_llm
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
    provider: str,
    api_key: str,
    history: list[dict] | None = None,
    expense_categories: list[str] | None = None,
    income_categories: list[str] | None = None,
    expense_category_tree: list[dict] | None = None,
    income_category_tree: list[dict] | None = None,
    expense_category_index: dict[str, str] | None = None,
    income_category_index: dict[str, str] | None = None,
    expense_subcategory_index: dict[str, dict[str, str]] | None = None,
    income_subcategory_index: dict[str, dict[str, str]] | None = None,
    accounts: list[str] | None = None,
    account_name_to_id: dict[str, str] | None = None,
) -> dict:
    """Run the agent graph and return response_type, message, and data.

    Args:
        message: The current user message.
        provider: LLM provider to use (google or groq).
        api_key: API key for the selected provider.
        history: Optional list of previous messages (dicts with role/content).
        expense_categories: Expense category names for the user.
        income_categories: Income category names for the user.
        expense_category_tree: Hierarchical structure [{category, subcategories[]}] for expenses.
        income_category_tree: Hierarchical structure [{category, subcategories[]}] for incomes.
        expense_subcategory_index: Case-insensitive mapping category/subcategory -> subcategory_id.
        income_subcategory_index: Case-insensitive mapping category/subcategory -> subcategory_id.
        accounts: Account names for the user.
        account_name_to_id: Case-insensitive mapping account name -> account_id.
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
    llm = get_llm(provider=provider, api_key=api_key)

    result = await _agent.ainvoke(
        {
            "messages": messages,
            "llm": llm,
            "expense_categories": expense_categories or [],
            "income_categories": income_categories or [],
            "expense_category_tree": expense_category_tree or [],
            "income_category_tree": income_category_tree or [],
            "expense_category_index": expense_category_index or {},
            "income_category_index": income_category_index or {},
            "expense_subcategory_index": expense_subcategory_index or {},
            "income_subcategory_index": income_subcategory_index or {},
            "accounts": accounts or [],
            "account_name_to_id": account_name_to_id or {},
        }
    )

    last_ai_message = result["messages"][-1]

    return {
        "response_type": result.get("response_type", "answer"),
        "message": last_ai_message.content,
        "data": result.get("response_payload"),
    }
