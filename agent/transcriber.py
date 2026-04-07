# agent/transcriber.py — Transcripcion de audio con Groq Whisper
# Generado por AgentKit para Elara

"""
Transcribe audios de WhatsApp a texto usando Groq Whisper API (gratis).
Compatible tambien con OpenAI Whisper cambiando URL y key en .env.
"""

import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("elara")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TRANSCRIPTION_API_URL = os.getenv(
    "TRANSCRIPTION_API_URL",
    "https://api.groq.com/openai/v1/audio/transcriptions"
)
TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")


def _extension_from_mimetype(mimetype: str) -> str:
    """Convierte mimetype a extension de archivo."""
    mime = mimetype.split(";")[0].strip().lower()
    extensiones = {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/amr": ".amr",
    }
    return extensiones.get(mime, ".ogg")


async def transcribir_audio(audio_bytes: bytes, mimetype: str = "audio/ogg") -> str | None:
    """
    Transcribe audio a texto usando Groq Whisper API.

    Args:
        audio_bytes: Bytes del archivo de audio
        mimetype: Tipo MIME del audio (ej: "audio/ogg; codecs=opus")

    Returns:
        Texto transcrito o None si falla
    """
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY no configurada — no se puede transcribir audio")
        return None

    ext = _extension_from_mimetype(mimetype)
    filename = f"audio{ext}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                TRANSCRIPTION_API_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (filename, audio_bytes, mimetype.split(";")[0].strip())},
                data={
                    "model": TRANSCRIPTION_MODEL,
                    "language": "es",
                    "response_format": "text",
                },
            )

            if r.status_code == 200:
                texto = r.text.strip()
                logger.info(f"Audio transcrito ({len(audio_bytes)} bytes): {texto[:100]}")
                return texto

            logger.error(f"Error transcripcion: {r.status_code} — {r.text[:200]}")
            return None

    except Exception as e:
        logger.error(f"Error al transcribir audio: {e}")
        return None
