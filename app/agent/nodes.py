from datetime import date
from math import floor

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
    category_tree = state.get("expense_category_tree", [])
    if category_tree:
        cat_lines = []
        for item in category_tree:
            name = str(item.get("category", ""))
            subcategories = item.get("subcategories", [])
            if subcategories:
                cat_lines.append(f"- {name}: {', '.join(subcategories)}")
            else:
                cat_lines.append(f"- {name}")
        cat_text = "\n".join(cat_lines)
    else:
        cat_text = "Inferí la categoría."

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
    category_tree = state.get("income_category_tree", [])
    if category_tree:
        cat_lines = []
        for item in category_tree:
            name = str(item.get("category", ""))
            subcategories = item.get("subcategories", [])
            if subcategories:
                cat_lines.append(f"- {name}: {', '.join(subcategories)}")
            else:
                cat_lines.append(f"- {name}")
        cat_text = "\n".join(cat_lines)
    else:
        cat_text = "Inferí la categoría."

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


def _resolve_subcategory_id(
    category_name: str,
    subcategory_name: str,
    subcategory_index: dict[str, dict[str, str]],
) -> tuple[str, str | None]:
    for indexed_category_name, subcategories in subcategory_index.items():
        if indexed_category_name.lower() != category_name.lower():
            continue

        for indexed_subcategory_name, subcategory_id in subcategories.items():
            if indexed_subcategory_name.lower() == subcategory_name.lower():
                return indexed_subcategory_name, subcategory_id

    return subcategory_name, None


def _resolve_category_id(category_name: str, category_index: dict[str, str]) -> tuple[str, str | None]:
    for indexed_category_name, category_id in category_index.items():
        if indexed_category_name.lower() == category_name.lower():
            return indexed_category_name, category_id
    return category_name, None


def _format_amount_es_ar(amount: float) -> str:
    # Convert 1,234,567.89 -> 1.234.567,89
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", "#").replace(".", ",").replace("#", ".")


def _resolve_account_id(
    account_name: str,
    accounts: list[str],
    account_name_to_id: dict[str, str],
) -> tuple[str, str | None]:
    normalized_name = _fuzzy_match(account_name, accounts) if accounts else account_name
    return normalized_name, account_name_to_id.get(normalized_name.strip().lower())


def _build_account_clarification_message(
    *,
    missing_fields: list[str],
    invalid_account_values: dict[str, str],
    accounts: list[str],
) -> str:
    issues: list[str] = []

    if "account" in missing_fields:
        issues.append("la cuenta de origen")
    if "account_destination" in missing_fields:
        issues.append("la cuenta destino")

    invalid_origin = invalid_account_values.get("account")
    if invalid_origin:
        issues.append(f"la cuenta de origen '{invalid_origin}' no existe")

    invalid_destination = invalid_account_values.get("account_destination")
    if invalid_destination:
        issues.append(f"la cuenta destino '{invalid_destination}' no existe")

    if issues:
        if len(issues) == 1:
            message = f"Necesito que aclares {issues[0]}."
        else:
            message = f"Necesito que aclares {', '.join(issues[:-1])} y {issues[-1]}."
    else:
        message = "Necesito que aclares la cuenta para poder registrar la transacción."

    if accounts:
        return f"{message} Cuentas disponibles: {', '.join(accounts)}."

    return f"{message} Primero creá una cuenta para poder registrar la transacción."


def validate(state: AgentState) -> dict:
    """Validate extracted fields against user's real accounts and categories."""
    data = dict(state["extractor_output"])
    subtype = state["classifier_output"].subtype
    accounts = state.get("accounts", [])
    account_name_to_id = state.get("account_name_to_id", {})

    # Add transaction type
    data["type"] = subtype

    missing_account_fields: list[str] = []
    invalid_account_values: dict[str, str] = {}

    # Validate and resolve source account to account_id
    account_name = data.get("account")
    if isinstance(account_name, str) and account_name.strip():
        normalized_account_name, account_id = _resolve_account_id(
            account_name,
            accounts,
            account_name_to_id,
        )
        data["account"] = normalized_account_name
        data["account_id"] = account_id
        if account_id is None:
            invalid_account_values["account"] = account_name
    else:
        missing_account_fields.append("account")
        data["account_id"] = None

    # Validate and resolve destination account for transfers
    if subtype == "transfer":
        destination_name = data.get("account_destination")
        if isinstance(destination_name, str) and destination_name.strip():
            normalized_destination_name, destination_account_id = _resolve_account_id(
                destination_name,
                accounts,
                account_name_to_id,
            )
            data["account_destination"] = normalized_destination_name
            data["account_destination_id"] = destination_account_id
            if destination_account_id is None:
                invalid_account_values["account_destination"] = destination_name
        else:
            missing_account_fields.append("account_destination")
            data["account_destination_id"] = None
    else:
        data["account_destination_id"] = None

    if missing_account_fields or invalid_account_values:
        return {
            "response_type": "clarification",
            "response_payload": None,
            "messages": [
                AIMessage(
                    content=_build_account_clarification_message(
                        missing_fields=missing_account_fields,
                        invalid_account_values=invalid_account_values,
                        accounts=accounts,
                    )
                )
            ],
        }

    # Validate category
    if "category" in data:
        if subtype == "expense":
            categories = state.get("expense_categories", [])
            category_index = state.get("expense_category_index", {})
        elif subtype == "income":
            categories = state.get("income_categories", [])
            category_index = state.get("income_category_index", {})
        else:
            categories = []
            category_index = {}

        if categories:
            data["category"] = _fuzzy_match(data["category"], categories)

        if data.get("category"):
            normalized_category_name, category_id = _resolve_category_id(data["category"], category_index)
            data["category_name"] = normalized_category_name
            data["category_id"] = category_id
        else:
            data["category_name"] = None
            data["category_id"] = None

    # Resolve subcategory_name -> subcategory_id
    if "subcategory_name" in data and data.get("subcategory_name"):
        category_name = data.get("category_name") or data.get("category")
        if category_name:
            if subtype == "expense":
                subcategory_index = state.get("expense_subcategory_index", {})
            elif subtype == "income":
                subcategory_index = state.get("income_subcategory_index", {})
            else:
                subcategory_index = {}

            normalized_subcategory_name, subcategory_id = _resolve_subcategory_id(
                category_name=category_name,
                subcategory_name=data["subcategory_name"],
                subcategory_index=subcategory_index,
            )
            data["subcategory_name"] = normalized_subcategory_name
            data["subcategory_id"] = subcategory_id
        else:
            data["subcategory_id"] = None

    # If installments are present, include the per-installment base amount.
    installments = data.get("installments")
    if isinstance(installments, int) and installments > 0:
        per_installment = data["amount"] / installments
        data["installment_amount"] = floor(per_installment * 100) / 100

    # Build summary message
    parts = [f"${_format_amount_es_ar(data['amount'])}", data.get("description", "")]
    if data.get("account"):
        parts.append(f"({data['account']})")
    if data.get("category_name"):
        parts.append(f"[{data['category_name']}]")
    if data.get("subcategory_name"):
        parts.append(f"<{data['subcategory_name']}>")

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
