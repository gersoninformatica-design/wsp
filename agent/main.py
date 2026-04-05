# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit para Elara

"""
Servidor principal de Elara. Recibe mensajes de WhatsApp via Evolution API,
genera respuestas con IA y las envia de vuelta. Detecta alertas urgentes
de Naxito y notifica directamente a Gerson.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.tools import notificar_gerson

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("elara")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Deduplicacion simple de mensajes
_mensajes_procesados: set[str] = set()
_MAX_CACHE = 1000

# Almacen temporal del QR (para el script qr.py)
_ultimo_qr: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor Elara corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="Elara — Secretaria Virtual del Sr. Gerson",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para monitoreo."""
    return {"status": "ok", "service": "elara"}


@app.get("/qrcode")
async def obtener_qr():
    """Retorna el ultimo QR recibido via webhook (para script qr.py)."""
    return _ultimo_qr


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificacion GET del webhook (requerido por Meta, no-op para Evolution)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.
    Procesa el mensaje, genera respuesta con Elara y la envia de vuelta.
    Detecta alertas urgentes de Naxito.
    """
    try:
        import json as _json
        import time as _time
        body_bytes = await request.body()
        body_json = {}
        try:
            body_json = _json.loads(body_bytes)
        except Exception:
            pass

        # Capturar evento QRCODE_UPDATED antes de parsear mensajes
        evento = body_json.get("event", "")
        if evento in ("qrcode.updated", "QRCODE_UPDATED"):
            qr_data = body_json.get("data", {})
            qr_obj = qr_data.get("qrcode", {}) if isinstance(qr_data.get("qrcode"), dict) else {}
            b64 = qr_obj.get("base64") or qr_data.get("base64", "")
            _ultimo_qr["base64"] = b64
            _ultimo_qr["timestamp"] = _time.time()
            logger.info("QR recibido via webhook")
            return {"status": "ok"}

        mensajes = await proveedor.parsear_webhook_body(body_json)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            # Deduplicacion: evitar procesar el mismo mensaje dos veces
            if msg.mensaje_id in _mensajes_procesados:
                continue
            _mensajes_procesados.add(msg.mensaje_id)
            if len(_mensajes_procesados) > _MAX_CACHE:
                # Limpiar la mitad mas antigua
                to_remove = list(_mensajes_procesados)[:_MAX_CACHE // 2]
                for item in to_remove:
                    _mensajes_procesados.discard(item)

            nombre = f" ({msg.nombre_contacto})" if msg.nombre_contacto else ""
            logger.info(f"Mensaje de {msg.telefono}{nombre}: {msg.texto}")

            # Obtener historial de la conversacion
            historial = await obtener_historial(msg.telefono)

            # Generar respuesta con IA
            respuesta = await generar_respuesta(msg.texto, historial)

            # Detectar alerta urgente de Naxito
            if "[ALERTA_GERSON]" in respuesta:
                respuesta = respuesta.replace("[ALERTA_GERSON]", "").strip()
                await notificar_gerson(msg.telefono, msg.texto)
                logger.info(f"ALERTA URGENTE de Naxito enviada a Gerson desde {msg.telefono}")

            # Guardar mensajes en memoria
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta por WhatsApp
            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
