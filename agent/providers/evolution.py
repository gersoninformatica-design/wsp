# agent/providers/evolution.py — Adaptador para Evolution API
# Generado por AgentKit para Elara

"""
Proveedor de WhatsApp usando Evolution API (open source, self-hosted).
Se conecta via QR code a WhatsApp Web usando el protocolo Baileys.
"""

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("elara")


class ProveedorEvolution(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Evolution API."""

    def __init__(self):
        self.api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self.api_key = os.getenv("EVOLUTION_API_KEY", "")
        self.instance = os.getenv("EVOLUTION_INSTANCE", "elara")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Evolution API (evento MESSAGES_UPSERT)."""
        body = await request.json()
        mensajes = []

        evento = body.get("event")
        if evento != "messages.upsert":
            return mensajes

        data = body.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})

        # Obtener el JID del remitente
        remote_jid = key.get("remoteJid", "")

        # Ignorar mensajes de grupos
        if "@g.us" in remote_jid:
            return mensajes

        # Limpiar numero: quitar @s.whatsapp.net
        telefono = remote_jid.replace("@s.whatsapp.net", "")

        # Extraer texto del mensaje (puede venir en distintos campos)
        texto = (
            message.get("conversation")
            or (message.get("extendedTextMessage", {}) or {}).get("text")
            or ""
        )

        # Si no es texto (imagen, audio, etc.), ignorar
        if not texto:
            return mensajes

        mensajes.append(MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=key.get("id", ""),
            es_propio=key.get("fromMe", False),
            nombre_contacto=data.get("pushName", ""),
        ))

        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envia mensaje via Evolution API."""
        if not self.api_key:
            logger.warning("EVOLUTION_API_KEY no configurada — mensaje no enviado")
            return False

        url = f"{self.api_url}/message/sendText/{self.instance}"
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        # Usar el JID tal como viene (puede ser @lid, @s.whatsapp.net, etc)
        # Si no tiene @, agregar @s.whatsapp.net
        numero = telefono if "@" in telefono else f"{telefono}@s.whatsapp.net"
        payload = {
            "number": numero,
            "text": mensaje,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code not in (200, 201):
                    logger.error(f"Error Evolution API: {r.status_code} — {r.text}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Error enviando mensaje via Evolution API: {e}")
            return False
