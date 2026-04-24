from __future__ import annotations

import logging

from groq import AsyncGroq
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="", tags=["transcribe"])

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MODEL_NAME = "whisper-large-v3-turbo"
TRANSCRIPTION_PROMPT = (
    "Transcribí el siguiente audio exactamente como fue dicho, en el idioma original. "
    "Devolvé únicamente la transcripción, sin explicaciones, sin puntuación adicional, "
    "sin prefijos como 'Transcripción:'."
)

groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)


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


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str, mime_type: str) -> str:
    transcription = await groq_client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=MODEL_NAME,
        temperature=0,
        response_format="verbose_json",
    )
    transcript = (transcription.text or "").strip()
    if not transcript:
        raise ValueError("Groq returned an empty transcription")

    return transcript


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> TranscriptionResponse:
    _ = current_user

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

    try:
        filename = _build_filename(audio.content_type)
        transcript = await transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            filename=filename,
            mime_type=audio.content_type,
        )

        return TranscriptionResponse(transcript=transcript)
    except ValueError as exc:
        logger.exception("Groq returned an empty transcription")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Groq devolvio una transcripcion vacia",
        ) from exc
    except Exception as exc:
        logger.exception("Error while transcribing audio with Groq")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se pudo transcribir el audio",
        ) from exc
