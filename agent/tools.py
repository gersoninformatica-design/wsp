# agent/tools.py — Herramientas de Elara
# Generado por AgentKit para Elara

"""
Herramientas especificas para Elara: manejo de hora chilena,
notificaciones urgentes a Gerson, y logica de horarios.
"""

import os
import yaml
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger("elara")

ZONA_CHILE = ZoneInfo("America/Santiago")

DIAS_SEMANA = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}


def obtener_hora_chile(hora_override: str | None = None) -> dict:
    """
    Retorna la hora actual en Chile con contexto util.

    Args:
        hora_override: Hora manual para testing (formato "HH:MM")

    Returns:
        dict con hora, dia_semana, fecha_legible, es_laboral, etc.
    """
    ahora = datetime.now(ZONA_CHILE)

    if hora_override:
        try:
            h, m = hora_override.split(":")
            ahora = ahora.replace(hour=int(h), minute=int(m))
        except (ValueError, IndexError):
            pass

    dia_num = ahora.weekday()  # 0=lunes, 6=domingo
    dia_nombre = DIAS_SEMANA[dia_num]
    hora_str = ahora.strftime("%H:%M")

    # Verificar si estamos en horario laboral (L-V 08:00-16:15)
    es_dia_laboral = dia_num < 5
    hora_actual = ahora.time()
    en_horario_laboral = es_dia_laboral and time(8, 0) <= hora_actual <= time(16, 15)

    # Verificar cortes horarios
    antes_naxito_corte = hora_actual <= time(16, 15)
    antes_personal_corte = hora_actual <= time(17, 0)

    return {
        "hora": hora_str,
        "dia_semana": dia_nombre,
        "dia_num": dia_num,
        "fecha_legible": ahora.strftime("%d de %B de %Y").replace(
            "January", "enero").replace("February", "febrero").replace(
            "March", "marzo").replace("April", "abril").replace(
            "May", "mayo").replace("June", "junio").replace(
            "July", "julio").replace("August", "agosto").replace(
            "September", "septiembre").replace("October", "octubre").replace(
            "November", "noviembre").replace("December", "diciembre"),
        "es_dia_laboral": es_dia_laboral,
        "en_horario_laboral": en_horario_laboral,
        "antes_naxito_corte": antes_naxito_corte,
        "antes_personal_corte": antes_personal_corte,
    }


def cargar_info_negocio() -> dict:
    """Carga la configuracion desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


async def notificar_gerson(telefono_remitente: str, contexto: str) -> bool:
    """
    Envia una alerta urgente al numero de Gerson sobre Naxito.
    Usa el provider de WhatsApp configurado para enviar el mensaje.

    Args:
        telefono_remitente: Numero de quien envio el mensaje urgente
        contexto: El mensaje original del remitente

    Returns:
        True si se envio correctamente
    """
    gerson_phone = os.getenv("GERSON_PHONE")
    if not gerson_phone:
        logger.warning("GERSON_PHONE no configurado — alerta no enviada")
        return False

    from agent.providers import obtener_proveedor
    proveedor = obtener_proveedor()

    alerta = (
        f"🚨 *ALERTA URGENTE — NAXITO*\n\n"
        f"Alguien necesita comunicarse urgentemente contigo sobre Naxito.\n\n"
        f"De: {telefono_remitente}\n"
        f"Mensaje: {contexto}\n\n"
        f"— Elara"
    )

    try:
        resultado = await proveedor.enviar_mensaje(gerson_phone, alerta)
        if resultado:
            logger.info(f"Alerta urgente enviada a Gerson desde {telefono_remitente}")
        return resultado
    except Exception as e:
        logger.error(f"Error enviando alerta a Gerson: {e}")
        return False
