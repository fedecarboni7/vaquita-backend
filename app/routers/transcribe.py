from __future__ import annotations

import base64
import json
import logging
from typing import Any

from groq import AsyncGroq
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.models.agent_usage import UsageType
from app.models.user import User
from app.schemas.chat import SessionApiKeyPayload
from app.services.ai_access import (
    INVALID_API_KEY_MESSAGE,
    is_llm_provider_auth_error,
    resolve_api_credentials,
)

router = APIRouter(prefix="", tags=["transcribe"])

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024
GROQ_TRANSCRIBE_MODEL_NAME = "whisper-large-v3-turbo"


class TranscriptionResponse(BaseModel):
    transcript: str


def _mime_type_to_extension(mime_type: str | None) -> str:
    if mime_type in {"audio/webm", "audio/webm;codecs=opus"}:
        return ".webm"
    if mime_type in {"audio/ogg", "audio/ogg;codecs=opus"}:
        return ".ogg"
    if mime_type in {"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"}:
        return ".m4a"
    if mime_type == "audio/mpeg":
        return ".mp3"
    if mime_type == "audio/wav":
        return ".wav"
    return ".webm"


def _build_filename(content_type: str | None) -> str:
    return f"audio{_mime_type_to_extension(content_type)}"


def _extract_response_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str):
                    stripped = value.strip()
                    if stripped:
                        text_parts.append(stripped)
        return "\n".join(text_parts).strip()

    return ""


def _parse_session_api_key(raw_session_api_key: str | None) -> SessionApiKeyPayload | None:
    if raw_session_api_key is None:
        return None

    try:
        parsed_payload = json.loads(raw_session_api_key)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid session_api_key payload",
        ) from exc

    if not isinstance(parsed_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid session_api_key payload",
        )

    try:
        return SessionApiKeyPayload.model_validate(parsed_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid session_api_key payload",
        ) from exc


async def _transcribe_with_groq(
    *,
    audio_bytes: bytes,
    filename: str,
    api_key: str,
) -> str:
    groq_client = AsyncGroq(api_key=api_key)
    transcription = await groq_client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=GROQ_TRANSCRIBE_MODEL_NAME,
        temperature=0,
        response_format="verbose_json",
    )
    transcript = (transcription.text or "").strip()
    if not transcript:
        raise ValueError("Groq returned an empty transcription")

    return transcript


async def _transcribe_with_google(
    *,
    audio_bytes: bytes,
    mime_type: str,
    api_key: str,
) -> str:
    llm = ChatGoogleGenerativeAI(
        model=settings.GOOGLE_DEFAULT_MODEL,
        google_api_key=api_key,
    )
    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
    prompt = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Transcribí este audio de forma literal y devolvé únicamente la transcripción, "
                    "sin explicaciones adicionales."
                ),
            },
            {
                "type": "media",
                "data": encoded_audio,
                "mime_type": mime_type,
            },
        ]
    )
    response = await llm.ainvoke([prompt])
    transcript = _extract_response_text(response.content)
    if not transcript:
        raise ValueError("Google returned an empty transcription")

    return transcript


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    session_api_key: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TranscriptionResponse:
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser de audio",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El audio enviado esta vacio",
        )

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El audio excede el tamano maximo permitido",
        )

    parsed_session_api_key = _parse_session_api_key(session_api_key)

    try:
        resolved_credentials = await resolve_api_credentials(
            current_user=current_user,
            session=session,
            usage_type=UsageType.transcribe,
            session_api_key=parsed_session_api_key,
        )
        filename = _build_filename(audio.content_type)
        if resolved_credentials.provider == "google":
            transcript = await _transcribe_with_google(
                audio_bytes=audio_bytes,
                mime_type=audio.content_type,
                api_key=resolved_credentials.api_key,
            )
        elif resolved_credentials.provider == "groq":
            transcript = await _transcribe_with_groq(
                audio_bytes=audio_bytes,
                filename=filename,
                api_key=resolved_credentials.api_key,
            )
        else:
            raise ValueError(f"Unsupported provider: {resolved_credentials.provider}")

        return TranscriptionResponse(transcript=transcript)
    except HTTPException:
        raise
    except ValueError as exc:
        logger.exception("Provider returned an empty transcription")
        if is_llm_provider_auth_error(exc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_API_KEY_MESSAGE,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El proveedor devolvió una transcripción vacía",
        ) from exc
    except Exception as exc:
        logger.exception("Error while transcribing audio")
        if is_llm_provider_auth_error(exc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_API_KEY_MESSAGE,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se pudo transcribir el audio",
        ) from exc
