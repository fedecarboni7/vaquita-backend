from typing import Any

from langgraph.graph import MessagesState

from app.agent.schemas import ClassifierOutput


class AgentState(MessagesState):
    classifier_output: ClassifierOutput | None = None
    extractor_output: dict[str, Any] | None = None
    response_type: str | None = None
    response_payload: dict[str, Any] | None = None
    expense_categories: list[str] = []
    income_categories: list[str] = []
    expense_category_tree: list[dict[str, Any]] = []
    income_category_tree: list[dict[str, Any]] = []
    expense_category_index: dict[str, str] = {}
    income_category_index: dict[str, str] = {}
    expense_subcategory_index: dict[str, dict[str, str]] = {}
    income_subcategory_index: dict[str, dict[str, str]] = {}
    accounts: list[str] = []
    account_name_to_id: dict[str, str] = {}
