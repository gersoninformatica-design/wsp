# agent/providers/evolution.py — Adaptador para Evolution API v1
# Generado por AgentKit para Elara

"""
Proveedor de WhatsApp usando Evolution API v1 (open source, self-hosted).
Se conecta via QR code a WhatsApp Web usando el protocolo Baileys.
Resolucion automatica de JIDs @lid (contactos con privacidad activada).
"""

import os
import json
import base64
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
        # Cache en memoria de @lid → numero (se carga al iniciar)
        self._lid_cache: dict[str, str] = {}

    async def cargar_contactos(self):
        """Carga mapeos @lid → numero desde Evolution API y BD al iniciar."""
        # Capa 1: cargar desde BD (contactos ya conocidos)
        from agent.memory import obtener_todos_contactos
        contactos_bd = await obtener_todos_contactos()
        self._lid_cache.update(contactos_bd)
        logger.info(f"Contactos cargados desde BD: {len(contactos_bd)}")

        # Capa 2: cargar desde Evolution API (fetchAllContacts)
        headers = {"apikey": self.api_key}
        try:
            url = f"{self.api_url}/chat/fetchAllContacts/{self.instance}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    contactos = r.json()
                    nuevos = 0
                    if isinstance(contactos, list):
                        for c in contactos:
                            jid = c.get("id") or c.get("remoteJid") or ""
                            # Buscar contactos que tengan @lid y tambien info de numero
                            if "@lid" in jid:
                                # Buscar si hay un owner o number field
                                numero = c.get("number") or c.get("notify") or ""
                                if numero and numero.isdigit():
                                    self._lid_cache[jid] = numero
                                    nuevos += 1
                    logger.info(f"Contactos desde Evolution API: {nuevos} nuevos @lid mapeados")
                else:
                    logger.warning(f"fetchAllContacts: {r.status_code}")
        except Exception as e:
            logger.warning(f"No se pudo cargar contactos desde Evolution: {e}")

        logger.info(f"Cache @lid total: {len(self._lid_cache)} contactos")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Evolution API (evento MESSAGES_UPSERT)."""
        body = await request.json()
        return await self._parsear_body(body)

    async def parsear_webhook_body(self, body: dict) -> list[MensajeEntrante]:
        """Parsea el body ya deserializado."""
        return await self._parsear_body(body)

    async def _parsear_body(self, body: dict) -> list[MensajeEntrante]:
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

        # Manejar audios y notas de voz
        if not texto and (message.get("audioMessage") or message.get("pttMessage")):
            audio_msg = message.get("audioMessage") or message.get("pttMessage")
            mimetype = (audio_msg.get("mimetype") or "audio/ogg").split(";")[0].strip()
            media = await self._descargar_audio(key)
            if media:
                from agent.transcriber import transcribir_audio
                texto = await transcribir_audio(media, mimetype)
                if texto:
                    texto = f"[Audio transcrito]: {texto}"
                else:
                    texto = "[El contacto envio un audio pero no se pudo transcribir]"
            else:
                texto = "[El contacto envio un audio pero no se pudo descargar]"

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

    async def _descargar_audio(self, key: dict) -> bytes | None:
        """Descarga y decodifica audio via Evolution API."""
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "message": {
                "key": {
                    "remoteJid": key.get("remoteJid", ""),
                    "fromMe": key.get("fromMe", False),
                    "id": key.get("id", ""),
                }
            },
            "convertToMp4": False,
        }

        try:
            url = f"{self.api_url}/chat/getBase64FromMediaMessage/{self.instance}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (200, 201):
                    data = r.json()
                    b64 = data.get("base64", "")
                    if b64:
                        audio_bytes = base64.b64decode(b64)
                        logger.info(f"Audio descargado: {len(audio_bytes)} bytes")
                        return audio_bytes
                logger.error(f"Error descargando audio: {r.status_code} — {r.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error al descargar audio de Evolution: {e}")
            return None

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envia mensaje via Evolution API v1 con resolucion automatica de @lid."""
        if not self.api_key:
            logger.warning("EVOLUTION_API_KEY no configurada — mensaje no enviado")
            return False

        numero = await self._resolver_numero(telefono)

        url = f"{self.api_url}/message/sendText/{self.instance}"
        payload = {
            "number": numero,
            "textMessage": {"text": mensaje},
        }

        body = json.dumps(payload, ensure_ascii=False)
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

        logger.debug(f"Enviando a {url} | number={numero}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, content=body.encode("utf-8"), headers=headers)
                if r.status_code in (200, 201):
                    logger.info(f"Mensaje enviado a {numero}")
                    return True

                # Si fallo y era @lid, intentar con el JID completo como fallback
                if "@lid" in telefono and numero != telefono:
                    logger.warning(f"Fallo con {numero}, intentando JID completo: {telefono}")
                    payload["number"] = telefono
                    body2 = json.dumps(payload, ensure_ascii=False)
                    r2 = await client.post(url, content=body2.encode("utf-8"), headers=headers)
                    if r2.status_code in (200, 201):
                        logger.info(f"Mensaje enviado con JID @lid directo: {telefono}")
                        return True

                logger.error(f"Error Evolution API: {r.status_code} — {r.text}")
                return False
        except Exception as e:
            logger.error(f"Error enviando mensaje via Evolution API: {e}")
            return False

    async def _resolver_numero(self, telefono: str) -> str:
        """Resuelve un JID a un numero limpio para sendText. 3 capas."""
        # Contacto normal: quitar sufijo
        if "@s.whatsapp.net" in telefono:
            return telefono.split("@")[0]

        # No es @lid: devolver tal cual
        if "@lid" not in telefono:
            return telefono

        # === @lid: resolver con 3 capas ===

        # Capa 1: cache en memoria (mas rapido)
        if telefono in self._lid_cache:
            logger.info(f"@lid resuelto (cache): {telefono} -> {self._lid_cache[telefono]}")
            return self._lid_cache[telefono]

        # Capa 2: buscar en BD
        from agent.memory import buscar_por_lid
        numero_bd = await buscar_por_lid(telefono)
        if numero_bd:
            self._lid_cache[telefono] = numero_bd
            logger.info(f"@lid resuelto (BD): {telefono} -> {numero_bd}")
            return numero_bd

        # Capa 3: buscar en Evolution API (contactos)
        numero_api = await self._buscar_en_evolution(telefono)
        if numero_api:
            self._lid_cache[telefono] = numero_api
            # Guardar en BD para futuro
            from agent.memory import guardar_contacto
            await guardar_contacto(telefono, numero_api)
            logger.info(f"@lid resuelto (API): {telefono} -> {numero_api}")
            return numero_api

        # No resuelto: quitar sufijo como ultimo recurso
        logger.warning(f"@lid no resuelto: {telefono}")
        return telefono.split("@")[0]

    async def _buscar_en_evolution(self, jid_lid: str) -> str | None:
        """Busca el numero real de un @lid en los contactos de Evolution."""
        headers = {"apikey": self.api_key}

        # Intentar findContacts
        try:
            url = f"{self.api_url}/chat/findContacts/{self.instance}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, json={"where": {"id": jid_lid}}, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    logger.info(f"findContacts respuesta para {jid_lid}: {json.dumps(data)[:500]}")
                    if isinstance(data, list) and data:
                        for contacto in data:
                            # Buscar cualquier campo con numero real
                            for campo in ("number", "jid", "remoteJid", "id"):
                                valor = contacto.get(campo, "")
                                if "@s.whatsapp.net" in str(valor):
                                    return str(valor).split("@")[0]
                            # Si tiene campo 'number' numerico
                            num = contacto.get("number", "")
                            if num and str(num).isdigit() and len(str(num)) > 8:
                                return str(num)
        except Exception as e:
            logger.debug(f"findContacts fallo: {e}")

        # Intentar fetchAllContacts (busqueda amplia)
        try:
            url = f"{self.api_url}/chat/fetchAllContacts/{self.instance}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    contactos = r.json()
                    lid_raw = jid_lid.split("@")[0]
                    if isinstance(contactos, list):
                        for c in contactos:
                            cid = c.get("id") or ""
                            if lid_raw in cid:
                                num = c.get("number", "")
                                if num and str(num).isdigit():
                                    return str(num)
        except Exception as e:
            logger.debug(f"fetchAllContacts fallo: {e}")

        return None

    async def registrar_contacto(self, jid: str, nombre: str = ""):
        """Registra un contacto @s.whatsapp.net en BD para futuro mapeo inverso."""
        if "@s.whatsapp.net" not in jid:
            return
        from agent.memory import guardar_contacto
        numero = jid.split("@")[0]
        # Guardamos con el JID completo como clave para referencia
        await guardar_contacto(jid, numero, nombre)
