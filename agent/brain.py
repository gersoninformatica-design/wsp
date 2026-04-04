# agent/brain.py — Cerebro del agente: conexion con OpenRouter
# Generado por AgentKit para Elara

"""
Logica de IA del agente. Lee el system prompt de prompts.yaml
y genera respuestas usando OpenRouter (formato OpenAI compatible).
"""

import os
import yaml
import logging
import httpx
from dotenv import load_dotenv
from agent.tools import obtener_hora_chile

load_dotenv()
logger = logging.getLogger("elara")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-6")


def cargar_config_prompts() -> dict:
    """Lee toda la configuracion desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente util. Responde en espanol.")


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado."""
    config = cargar_config_prompts()
    return config.get("error_message", "Disculpe, estoy experimentando problemas tecnicos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpe, no entendi su mensaje.")


async def generar_respuesta(mensaje: str, historial: list[dict], hora_override: str | None = None) -> str:
    """
    Genera una respuesta usando OpenRouter API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]
        hora_override: Hora manual para testing (formato "HH:MM")

    Returns:
        La respuesta generada por el modelo
    """
    if not mensaje or not mensaje.strip():
        return obtener_mensaje_fallback()

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "sk-or-PEGA-TU-KEY-AQUI":
        logger.error("OPENROUTER_API_KEY no configurada")
        return obtener_mensaje_error()

    # Construir system prompt con hora actual de Chile
    system_prompt = cargar_system_prompt()
    info_hora = obtener_hora_chile(hora_override)
    system_prompt += f"\n\n[Contexto del sistema] Hora actual en Chile: {info_hora['fecha_legible']}, {info_hora['hora']} hrs ({info_hora['dia_semana']})"

    # Construir mensajes en formato OpenAI
    mensajes = [{"role": "system", "content": system_prompt}]

    for msg in historial:
        mensajes.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Elara - Secretaria Virtual",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": mensajes,
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(f"Error OpenRouter: {response.status_code} — {response.text}")
                return obtener_mensaje_error()

            data = response.json()
            respuesta = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            logger.info(f"Respuesta generada ({usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out)")

            return respuesta

    except httpx.TimeoutException:
        logger.error("Timeout al conectar con OpenRouter")
        return obtener_mensaje_error()
    except Exception as e:
        logger.error(f"Error OpenRouter: {e}")
        return obtener_mensaje_error()
