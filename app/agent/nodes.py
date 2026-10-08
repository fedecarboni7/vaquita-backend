import logging
from datetime import date
from typing import Any, Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import ValidationError, create_model

from app.agent.prompts import PARSE_PROMPT
from app.agent.schemas import ParseOutput
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_PARSE_RETRYABLE_ERRORS = (ValidationError, OutputParserException, ValueError, TypeError)


def _get_runtime_llm(state: AgentState):
    llm = state.get("llm")
    if llm is None:
        raise ValueError("LLM is not available in agent state")
    return llm


def _invoke_with_retry(structured_llm, messages, attempts=2):
    """Invoke the structured LLM, retrying parse/validation errors once."""
    last_error = None
    for _ in range(attempts):
        try:
            return structured_llm.invoke(messages)
        except _PARSE_RETRYABLE_ERRORS as exc:
            last_error = exc
    raise last_error


def _render_pending_draft(pending: dict[str, Any] | None) -> str:
    if not pending:
        return "Ninguno."

    parts = []
    if pending.get("type"):
        parts.append(f"Tipo: {pending['type']}")
    if pending.get("description"):
        parts.append(f"Descripción: {pending['description']}")
    if pending.get("amount") is not None:
        parts.append(f"Monto: {pending['amount']}")
    if pending.get("account_id") is None and pending.get("type") in {"expense", "income"}:
        parts.append("Falta: cuenta")
    if pending.get("account_destination_id") is None and pending.get("type") == "transfer":
        parts.append("Falta: cuenta destino")
    return " | ".join(parts) if parts else "Ninguno."


def _build_parse_model(ctx: Any):
    account_values = list(dict.fromkeys(getattr(ctx, "account_codes", {}).values()))
    expense_category_values = list(dict.fromkeys(getattr(ctx, "expense_category_codes", {}).values()))
    income_category_values = list(dict.fromkeys(getattr(ctx, "income_category_codes", {}).values()))

    expense_subcategory_values = []
    for subitems in getattr(ctx, "expense_subcategory_codes", {}).values():
        expense_subcategory_values.extend(subitems.values())
    income_subcategory_values = []
    for subitems in getattr(ctx, "income_subcategory_codes", {}).values():
        income_subcategory_values.extend(subitems.values())

    account_field = Literal[tuple(account_values)] | None if account_values else type(None)
    category_field = (
        Literal[tuple(expense_category_values + income_category_values)] | None
        if (expense_category_values or income_category_values)
        else type(None)
    )
    subcategory_field = (
        Literal[tuple(expense_subcategory_values + income_subcategory_values)] | None
        if (expense_subcategory_values or income_subcategory_values)
        else type(None)
    )

    return create_model(
        "DynamicParseOutput",
        __base__=ParseOutput,
        kind=(Literal["transaction", "chat"], ...),
        reply=(str | None, None),
        tx_type=(Literal["expense", "income", "transfer"] | None, None),
        starts_new_transaction=(bool, False),
        amount_text=(str | None, None),
        to_amount_text=(str | None, None),
        description=(str | None, None),
        account=(account_field, None),
        account_destination=(account_field, None),
        category=(category_field, None),
        subcategory=(subcategory_field, None),
        date=(str | None, None),
        currency=(Literal["ARS", "USD"] | None, None),
        installments=(int | None, None),
        note=(str | None, None),
    )


def parse(state: AgentState) -> dict:
    """Parse the last user message into a structured patch."""
    llm = _get_runtime_llm(state)
    ctx = state.get("agent_context")
    schema = _build_parse_model(ctx)
    llm_model = llm.with_structured_output(schema)

    account_lines = []
    if getattr(ctx, "account_codes", {}):
        for name, code in getattr(ctx, "account_codes", {}).items():
            account_lines.append(f"{code} {name}")
    account_text = ", ".join(account_lines) if account_lines else "No hay cuentas definidas."

    expense_categories = getattr(ctx, "expense_category_codes", {})
    expense_category_lines = []
    for name, code in expense_categories.items():
        subitems = getattr(ctx, "expense_subcategory_codes", {}).get(code, {})
        if subitems:
            sub_text = ", ".join(f"{sub_code} {sub_name}" for sub_name, sub_code in subitems.items())
            expense_category_lines.append(f"{code} {name} → {sub_text}")
        else:
            expense_category_lines.append(f"{code} {name}")

    income_categories = getattr(ctx, "income_category_codes", {})
    income_category_lines = []
    for name, code in income_categories.items():
        subitems = getattr(ctx, "income_subcategory_codes", {}).get(code, {})
        if subitems:
            sub_text = ", ".join(f"{sub_code} {sub_name}" for sub_name, sub_code in subitems.items())
            income_category_lines.append(f"{code} {name} → {sub_text}")
        else:
            income_category_lines.append(f"{code} {name}")

    prompt = PARSE_PROMPT.replace("{accounts}", account_text)
    prompt = prompt.replace("{expense_categories}", "; ".join(expense_category_lines) or "Sin categorías de gastos.")
    prompt = prompt.replace("{income_categories}", "; ".join(income_category_lines) or "Sin categorías de ingresos.")
    prompt = prompt.replace("{today}", date.today().isoformat())
    prompt = prompt.replace("{pending_draft}", _render_pending_draft(state.get("pending_draft")))

    try:
        result = _invoke_with_retry(llm_model, [SystemMessage(content=prompt), *state["messages"]])
        return {"parse_output": result}
    except _PARSE_RETRYABLE_ERRORS:
        fallback = ParseOutput(kind="chat", reply="Uy, no pude entender eso. ¿Me lo repetís con otras palabras?")
        return {
            "parse_output": fallback,
            "messages": [AIMessage(content=fallback.reply)],
        }


def resolve(state: AgentState) -> dict:
    from app.agent.resolve import resolve_transaction

    result = resolve_transaction(
        patch=state["parse_output"],
        pending=state.get("pending_draft"),
        ctx=state.get("agent_context"),
        today=date.today(),
    )

    return {
        "response_type": result["response_type"],
        "response_payload": result["payload"],
        "messages": [AIMessage(content=result["message"])],
        "missing_fields": result.get("missing_fields", []),
        "inferred_fields": result.get("inferred_fields", []),
    }


def handle_chat(state: AgentState) -> dict:
    output = state["parse_output"]
    text = (
        output.reply
        or "¡Hola! Soy Vaquita, tu asistente de finanzas personales. Por ahora puedo ayudarte a registrar gastos, ingresos y transferencias — ya sea escribiendo o mandando un audio."
    )
    return {
        "response_type": "answer",
        "response_payload": None,
        "messages": [AIMessage(content=text)],
    }
