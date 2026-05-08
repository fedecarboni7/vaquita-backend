from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


def get_llm(provider: str, api_key: str) -> BaseChatModel:
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.GROQ_DEFAULT_MODEL,
            api_key=api_key,
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.GOOGLE_DEFAULT_MODEL,
            google_api_key=api_key,
        )

    raise ValueError(f"Unsupported provider: {provider}")


def get_fallback_llm(provider: str, api_key: str) -> BaseChatModel | None:
    if provider == "groq":
        if not settings.GROQ_FALLBACK_MODEL:
            return None
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.GROQ_FALLBACK_MODEL,
            api_key=api_key,
        )

    if provider == "google":
        if not settings.GOOGLE_FALLBACK_MODEL:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.GOOGLE_FALLBACK_MODEL,
            google_api_key=api_key,
        )

    return None
