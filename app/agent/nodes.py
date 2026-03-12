from datetime import date

from langchain_core.messages import AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.prompts import (
    CLASSIFIER_PROMPT,
    EXPENSE_EXTRACTOR_PROMPT,
    INCOME_EXTRACTOR_PROMPT,
    TRANSFER_EXTRACTOR_PROMPT,
)
from app.agent.schemas import (
    ClassifierOutput,
    ExpenseExtractorOutput,
    IncomeExtractorOutput,
    TransferExtractorOutput,
)
from app.agent.state import AgentState
from app.config import settings


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
    )


def classify(state: AgentState) -> dict:
    """Classify user intent using the LLM."""
    llm = _get_llm().with_structured_output(ClassifierOutput)

    system_msg = SystemMessage(content=CLASSIFIER_PROMPT.format(today=date.today().isoformat()))
    messages = [system_msg, *state["messages"]]
    result: ClassifierOutput = llm.invoke(messages)

    return {"classifier_output": result}


def extract_expense(state: AgentState) -> dict:
    """Extract expense fields from the user message."""
    llm = _get_llm().with_structured_output(ExpenseExtractorOutput)

    accounts = state.get("accounts", [])
    acc_text = ", ".join(accounts) if accounts else "No hay cuentas definidas."
    categories = state.get("expense_categories", [])
    cat_text = ", ".join(categories) if categories else "Inferí la categoría."

    system_msg = SystemMessage(
        content=EXPENSE_EXTRACTOR_PROMPT.format(
            accounts=acc_text,
            expense_categories=cat_text,
            today=date.today().isoformat(),
        )
    )
    result: ExpenseExtractorOutput = llm.invoke([system_msg, *state["messages"]])

    return {"extractor_output": result.model_dump(exclude_none=True)}


def extract_income(state: AgentState) -> dict:
    """Extract income fields from the user message."""
    llm = _get_llm().with_structured_output(IncomeExtractorOutput)

    accounts = state.get("accounts", [])
    acc_text = ", ".join(accounts) if accounts else "No hay cuentas definidas."
    categories = state.get("income_categories", [])
    cat_text = ", ".join(categories) if categories else "Inferí la categoría."

    system_msg = SystemMessage(
        content=INCOME_EXTRACTOR_PROMPT.format(
            accounts=acc_text,
            income_categories=cat_text,
            today=date.today().isoformat(),
        )
    )
    result: IncomeExtractorOutput = llm.invoke([system_msg, *state["messages"]])

    return {"extractor_output": result.model_dump(exclude_none=True)}


def extract_transfer(state: AgentState) -> dict:
    """Extract transfer fields from the user message."""
    llm = _get_llm().with_structured_output(TransferExtractorOutput)

    accounts = state.get("accounts", [])
    acc_text = ", ".join(accounts) if accounts else "No hay cuentas definidas."

    system_msg = SystemMessage(
        content=TRANSFER_EXTRACTOR_PROMPT.format(
            accounts=acc_text,
            today=date.today().isoformat(),
        )
    )
    result: TransferExtractorOutput = llm.invoke([system_msg, *state["messages"]])

    return {"extractor_output": result.model_dump(exclude_none=True)}


def _fuzzy_match(value: str, valid_options: list[str]) -> str:
    """Try case-insensitive match against valid options. Return original if no match."""
    lower = value.lower()
    for option in valid_options:
        if option.lower() == lower:
            return option
    return value


def validate(state: AgentState) -> dict:
    """Validate extracted fields against user's real accounts and categories."""
    data = dict(state["extractor_output"])
    subtype = state["classifier_output"].subtype
    accounts = state.get("accounts", [])

    # Add transaction type
    data["type"] = subtype

    # Validate account
    if "account" in data and accounts:
        data["account"] = _fuzzy_match(data["account"], accounts)

    # Validate account_destination for transfers
    if "account_destination" in data and accounts:
        data["account_destination"] = _fuzzy_match(data["account_destination"], accounts)

    # Validate category
    if "category" in data:
        if subtype == "expense":
            categories = state.get("expense_categories", [])
        elif subtype == "income":
            categories = state.get("income_categories", [])
        else:
            categories = []

        if categories:
            data["category"] = _fuzzy_match(data["category"], categories)

    # Build summary message
    parts = [f"${data['amount']:.2f}", data.get("description", "")]
    if data.get("account"):
        parts.append(f"({data['account']})")
    if data.get("category"):
        parts.append(f"[{data['category']}]")

    message = f"Registré: {' — '.join(parts)}"

    return {
        "response_type": "draft",
        "response_payload": data,
        "messages": [AIMessage(content=message)],
    }


def handle_clarification(state: AgentState) -> dict:
    """Return the clarification message from the classifier."""
    output = state["classifier_output"]
    text = output.clarification_message or "¿Podrías darme más detalles?"

    return {
        "response_type": "clarification",
        "response_payload": None,
        "messages": [AIMessage(content=text)],
    }


def handle_direct_answer(state: AgentState) -> dict:
    """Return the direct answer message from the classifier."""
    output = state["classifier_output"]
    text = (
        output.direct_answer_message
        or "Soy un asistente de finanzas personales. Podés registrar gastos, ingresos y transferencias mandándome un mensaje."
    )

    return {
        "response_type": "answer",
        "response_payload": None,
        "messages": [AIMessage(content=text)],
    }
