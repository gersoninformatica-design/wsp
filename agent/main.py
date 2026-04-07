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
    """Inicializa la base de datos y carga contactos al arrancar."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    # Seed: contactos @lid conocidos
    from agent.memory import guardar_contacto
    await guardar_contacto("63244114890831@lid", "56936150444", "Naxito")
    await guardar_contacto("188166946484295@lid", "56997121210", "Mamá")
    # Cargar cache de contactos @lid si el proveedor lo soporta
    if hasattr(proveedor, 'cargar_contactos'):
        await proveedor.cargar_contactos()
    logger.info(f"Servidor Elara corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


async def _aprender_contactos(body: dict):
    """Extrae mapeos @lid → numero de eventos contacts.upsert/update de Evolution."""
    import json as _json
    from agent.memory import guardar_contacto

    data = body.get("data", [])
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return

    for contacto in data:
        if not isinstance(contacto, dict):
            continue

        # Buscar el JID @lid y el numero real en los campos disponibles
        lid = ""
        numero = ""
        nombre = contacto.get("pushName") or contacto.get("name") or contacto.get("notify") or ""

        cid = contacto.get("id", "")
        lid_field = contacto.get("lid", "")

        # Caso 1: id es @s.whatsapp.net y lid tiene el @lid
        if "@s.whatsapp.net" in cid and lid_field and "@lid" in str(lid_field):
            numero = cid.split("@")[0]
            lid = str(lid_field) if "@lid" in str(lid_field) else ""

        # Caso 2: id es @lid y hay un campo number
        elif "@lid" in cid:
            lid = cid
            num = contacto.get("number", "")
            if num and str(num).isdigit() and len(str(num)) > 8:
                numero = str(num)

        # Caso 3: buscar en otros campos
        if not numero:
            for campo in ("number", "jid", "remoteJid", "owner"):
                val = str(contacto.get(campo, ""))
                if "@s.whatsapp.net" in val:
                    numero = val.split("@")[0]
                    break
                if val.isdigit() and len(val) > 8:
                    numero = val
                    break

        if lid and numero:
            await guardar_contacto(lid, numero, nombre)
            if hasattr(proveedor, '_lid_cache'):
                proveedor._lid_cache[lid] = numero
            logger.info(f"@lid auto-aprendido: {lid} -> {numero} ({nombre})")
        elif lid or "@lid" in str(contacto):
            # Log para investigar formatos desconocidos
            logger.info(f"Contacto con @lid sin resolver: {_json.dumps(contacto)[:300]}")


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

        # Log de todos los eventos webhook para diagnostico
        evento = body_json.get("event", "")
        if evento and evento != "messages.upsert":
            logger.info(f"Webhook evento: {evento}")
        if evento in ("qrcode.updated", "QRCODE_UPDATED"):
            qr_data = body_json.get("data", {})
            qr_obj = qr_data.get("qrcode", {}) if isinstance(qr_data.get("qrcode"), dict) else {}
            b64 = qr_obj.get("base64") or qr_data.get("base64", "")
            _ultimo_qr["base64"] = b64
            _ultimo_qr["timestamp"] = _time.time()
            logger.info("QR recibido via webhook")
            return {"status": "ok"}

        # Auto-aprender mapeos @lid desde eventos de contactos
        if evento in ("contacts.upsert", "contacts.update"):
            await _aprender_contactos(body_json)
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
