from datetime import date

from langchain_core.messages import AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import ClassifierOutput
from app.agent.state import AgentState
from app.config import settings


def _build_system_message(categories: list[str], accounts: list[str]) -> SystemMessage:
    cat_text = ", ".join(categories) if categories else "inferí la categoría."
    acc_text = ", ".join(accounts) if accounts else "el usuario puede usar cualquier cuenta."
    prompt = SYSTEM_PROMPT.format(
        categories=cat_text,
        accounts=acc_text,
        today=date.today().isoformat(),
    )
    return SystemMessage(content=prompt)


def classify(state: AgentState) -> dict:
    """Single LLM call that classifies intent and extracts structured data."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-flash-lite-latest",
        google_api_key=settings.GOOGLE_API_KEY,
    )
    structured_llm = llm.with_structured_output(ClassifierOutput)

    system_msg = _build_system_message(state.get("categories", []), state.get("accounts", []))
    messages = [system_msg, *state["messages"]]
    result: ClassifierOutput = structured_llm.invoke(messages)

    return {"classifier_output": result}


def handle_register(state: AgentState) -> dict:
    """Build a draft response from the classified register data."""
    output = state["classifier_output"]
    data = output.register_data

    payload = data.model_dump(exclude_none=True)

    summary_parts = [f"${data.amount:.2f}", data.description]
    if data.account:
        summary_parts.append(f"({data.account})")
    if data.category:
        summary_parts.append(f"[{data.category}]")

    message = f"Registré: {' — '.join(summary_parts)}"

    return {
        "response_type": "draft",
        "response_payload": payload,
        "messages": [AIMessage(content=message)],
    }


def handle_direct(state: AgentState) -> dict:
    """Handle direct_answer, clarification_needed, and out_of_scope intents."""
    output = state["classifier_output"]
    intent = output.intent

    if intent == "clarification_needed":
        text = output.clarification_message or "¿Podrías darme más detalles?"
        response_type = "clarification"
    elif intent == "direct_answer":
        text = output.direct_answer_data.message if output.direct_answer_data else "No tengo una respuesta para eso."
        response_type = "answer"
    else:  # out_of_scope
        text = "Eso está fuera de lo que puedo ayudarte. Soy un asistente de finanzas personales."
        response_type = "answer"

    return {
        "response_type": response_type,
        "response_payload": None,
        "messages": [AIMessage(content=text)],
    }
