import base64

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings

TRANSCRIPTION_PROMPT = (
    "Transcribí este audio exactamente como fue dicho, en español. "
    "Devolvé solo el texto, sin comentarios adicionales."
)


def _normalize_transcript_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text = block.strip()
                if text:
                    parts.append(text)
                continue

            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    clean_text = text.strip()
                    if clean_text:
                        parts.append(clean_text)

        return " ".join(parts).strip()

    return ""


async def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str) -> str:
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    if not audio_bytes:
        raise ValueError("Audio payload is empty")

    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
    )

    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
    message = HumanMessage(
        content=[
            {
                "type": "media",
                "mime_type": mime_type,
                "data": encoded_audio,
            },
            {
                "type": "text",
                "text": TRANSCRIPTION_PROMPT,
            },
        ]
    )

    response = await llm.ainvoke([message])
    transcript = _normalize_transcript_content(response.content)
    if not transcript:
        raise ValueError("Gemini transcription returned empty text")

    return transcript
