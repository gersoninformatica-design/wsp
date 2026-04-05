# agent/providers/evolution.py — Adaptador para Evolution API v1
# Generado por AgentKit para Elara

"""
Proveedor de WhatsApp usando Evolution API v1 (open source, self-hosted).
Se conecta via QR code a WhatsApp Web usando el protocolo Baileys.
Soporta JIDs @s.whatsapp.net y @lid (numeros con privacidad).
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
        return self._parsear_body(body)

    async def parsear_webhook_body(self, body: dict) -> list[MensajeEntrante]:
        """Parsea el body ya deserializado."""
        return self._parsear_body(body)

    def _parsear_body(self, body: dict) -> list[MensajeEntrante]:
        mensajes = []

        evento = body.get("event")
        if evento != "messages.upsert":
            return mensajes

        data = body.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})

        remote_jid = key.get("remoteJid", "")

        # Ignorar grupos
        if "@g.us" in remote_jid:
            return mensajes

        # Mantener el JID completo (incluyendo @lid si aplica)
        telefono = remote_jid

        texto = (
            message.get("conversation")
            or (message.get("extendedTextMessage", {}) or {}).get("text")
            or ""
        )

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
        """Envia mensaje via Evolution API v1."""
        if not self.api_key:
            logger.warning("EVOLUTION_API_KEY no configurada — mensaje no enviado")
            return False

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

        # Intentar primero con el JID original (funciona con @s.whatsapp.net)
        numero = telefono if "@" in telefono else f"{telefono}@s.whatsapp.net"

        # Si es @lid, intentar convertir a @s.whatsapp.net buscando el contacto
        if "@lid" in numero:
            numero_real = await self._buscar_numero_real(telefono, headers)
            if numero_real:
                numero = numero_real

        url = f"{self.api_url}/message/sendText/{self.instance}"
        payload = {
            "number": numero,
            "textMessage": {"text": mensaje},
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

    async def _buscar_numero_real(self, jid_lid: str, headers: dict) -> str | None:
        """Intenta encontrar el numero @s.whatsapp.net a partir de un JID @lid."""
        try:
            numero_raw = jid_lid.replace("@lid", "")
            url = f"{self.api_url}/contact/find/{self.instance}"
            params = f"?contactId={numero_raw}@lid"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url + params, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    # Buscar jid o remoteJid en los resultados
                    if isinstance(data, list) and data:
                        jid = data[0].get("remoteJid") or data[0].get("id") or ""
                        if "@s.whatsapp.net" in jid:
                            return jid
        except Exception as e:
            logger.debug(f"No se pudo resolver @lid: {e}")
        return None
