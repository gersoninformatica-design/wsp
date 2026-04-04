# tests/test_local.py — Simulador de chat en terminal
# Generado por AgentKit para Elara

"""
Prueba a Elara sin necesitar WhatsApp.
Simula una conversacion en la terminal.

Comandos especiales:
  'limpiar'      — borra el historial
  'salir'        — termina el test
  'hora HH:MM'   — simula una hora especifica (ej: hora 18:30)
  'hora reset'   — vuelve a la hora real
"""

import asyncio
import sys
import os

# Agregar el directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial

TELEFONO_TEST = "test-local-001"


async def main():
    """Loop principal del chat de prueba."""
    await inicializar_db()

    hora_override = None

    print()
    print("=" * 55)
    print("   Elara — Test Local")
    print("   Secretaria Virtual del Sr. Gerson")
    print("=" * 55)
    print()
    print("  Escribe mensajes como si fueras un contacto.")
    print("  Comandos especiales:")
    print("    'limpiar'      — borra el historial")
    print("    'salir'        — termina el test")
    print("    'hora HH:MM'   — simula una hora (ej: hora 18:30)")
    print("    'hora reset'   — vuelve a la hora real")
    print()
    print("-" * 55)
    print()

    while True:
        try:
            sufijo_hora = f" [simulando {hora_override}]" if hora_override else ""
            mensaje = input(f"Tu{sufijo_hora}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue

        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break

        if mensaje.lower() == "limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado]\n")
            continue

        if mensaje.lower().startswith("hora "):
            valor = mensaje[5:].strip()
            if valor.lower() == "reset":
                hora_override = None
                print("[Hora: usando hora real de Chile]\n")
            else:
                hora_override = valor
                print(f"[Hora simulada: {hora_override}]\n")
            continue

        # Obtener historial
        historial = await obtener_historial(TELEFONO_TEST)

        # Generar respuesta
        print("\nElara: ", end="", flush=True)
        respuesta = await generar_respuesta(mensaje, historial, hora_override)

        # Detectar alerta urgente (en test solo la muestra)
        if "[ALERTA_GERSON]" in respuesta:
            respuesta = respuesta.replace("[ALERTA_GERSON]", "").strip()
            print(respuesta)
            print("\n  [*** ALERTA URGENTE enviada a Gerson ***]")
        else:
            print(respuesta)

        print()

        # Guardar en memoria
        await guardar_mensaje(TELEFONO_TEST, "user", mensaje)
        await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta)


if __name__ == "__main__":
    asyncio.run(main())
