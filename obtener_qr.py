#!/usr/bin/env python3
# obtener_qr.py — Obtiene y muestra el QR de Evolution API v2.1.1 en terminal
# Solución al bug de reconexión infinita en v2.1.1 que impide generar el QR

"""
PROBLEMA CONFIRMADO:
  Evolution API v2.1.1 tiene un bug (Issue #2385 en GitHub) donde el endpoint
  /instance/connect siempre devuelve {"count": 0} porque Baileys entra en un
  loop infinito de reconexión antes de generar el QR.

ESTE SCRIPT:
  1. Borra la instancia actual (limpia el estado roto)
  2. Crea una instancia nueva forzando qrcode:true
  3. Hace polling del endpoint /instance/connect hasta obtener base64 != null
  4. Muestra el QR en terminal Y lo guarda como qr.html para abrir en el browser

USO:
  python3 obtener_qr.py

ALTERNATIVA (si este script tampoco funciona):
  Ejecutar upgrade_evolution.sh para actualizar a v2.2.3 que tiene el fix oficial.
"""

import asyncio
import base64
import io
import os
import sys
import time
import httpx

# Forzar UTF-8 en Windows (evita errores de encoding con caracteres especiales)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Configuración ──────────────────────────────────────────────────────────────
EVOLUTION_URL = "http://137.184.223.186:8080"
API_KEY       = "elara-prod-2026-xyz"
INSTANCE_NAME = "elara"
MAX_INTENTOS  = 30      # intentos máximos esperando el QR
PAUSA_SEGS    = 3       # segundos entre cada intento

HEADERS = {
    "apikey": API_KEY,
    "Content-Type": "application/json",
}

# ── Utilidades ────────────────────────────────────────────────────────────────

def imprimir(msg: str, emoji: str = ""):
    prefix = f"{emoji} " if emoji else "  "
    print(f"{prefix}{msg}")

def guardar_qr_html(base64_qr: str):
    """Guarda el QR como página HTML para abrir en el navegador."""
    # El campo 'code' de Evolution API ya viene como data:image/png;base64,...
    if not base64_qr.startswith("data:"):
        base64_qr = f"data:image/png;base64,{base64_qr}"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Code — Elara WhatsApp</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #f0f2f5;
    }}
    .card {{
      background: white;
      border-radius: 16px;
      padding: 32px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.1);
      text-align: center;
      max-width: 420px;
    }}
    h1 {{ color: #128C7E; margin-bottom: 8px; }}
    p  {{ color: #666; margin-bottom: 24px; }}
    img {{ width: 300px; height: 300px; border: 2px solid #eee; border-radius: 8px; }}
    .nota {{ font-size: 12px; color: #999; margin-top: 16px; }}
    .expira {{ color: #e74c3c; font-weight: bold; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Escanea el QR — Elara</h1>
    <p>Abre WhatsApp → Dispositivos vinculados → Vincular un dispositivo</p>
    <img src="{base64_qr}" alt="QR Code WhatsApp">
    <p class="nota expira">El QR expira en ~60 segundos. Si vence, ejecuta el script de nuevo.</p>
    <p class="nota">Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
  </div>
</body>
</html>"""

    with open("qr.html", "w", encoding="utf-8") as f:
        f.write(html)
    imprimir("QR guardado en qr.html — ábrelo en tu navegador", "💾")


def mostrar_qr_terminal(base64_qr: str):
    """Intenta mostrar el QR en terminal usando qrcode si está disponible."""
    try:
        import qrcode

        # El base64 es una imagen PNG, no el texto del QR.
        # Evolution API devuelve en 'code' el base64 de la imagen del QR.
        # Para mostrar en terminal necesitamos el texto raw del QR.
        # Intentamos decodificar la imagen y leer el QR con pyzbar si existe.
        try:
            import io
            from PIL import Image
            from pyzbar.pyzbar import decode as qr_decode

            raw = base64_qr
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            img_bytes = base64.b64decode(raw)
            img = Image.open(io.BytesIO(img_bytes))
            decoded = qr_decode(img)
            if decoded:
                qr_text = decoded[0].data.decode("utf-8")
                qr_obj = qrcode.QRCode()
                qr_obj.add_data(qr_text)
                qr_obj.make(fit=True)
                print("\n" + "═" * 60)
                print("  QR CODE — ESCANEA CON WHATSAPP")
                print("═" * 60)
                qr_obj.print_ascii(invert=True)
                print("═" * 60 + "\n")
                return
        except ImportError:
            pass  # pyzbar/Pillow no disponibles, usar solo HTML

    except ImportError:
        pass  # qrcode no disponible

    imprimir("No se puede mostrar QR en terminal (librerías no disponibles)")
    imprimir("Usa qr.html que se generó — ábrelo en el navegador")


# ── Lógica principal ──────────────────────────────────────────────────────────

async def borrar_instancia(client: httpx.AsyncClient) -> bool:
    """Borra la instancia para limpiar estado roto."""
    try:
        r = await client.delete(
            f"{EVOLUTION_URL}/instance/delete/{INSTANCE_NAME}",
            headers=HEADERS,
        )
        if r.status_code == 200:
            imprimir("Instancia anterior borrada", "✓")
            return True
        else:
            imprimir(f"No se pudo borrar (status {r.status_code}) — puede que no exista")
            return True  # Continuar igual
    except Exception as e:
        imprimir(f"Error al borrar instancia: {e}")
        return False


async def crear_instancia(client: httpx.AsyncClient) -> bool:
    """Crea una instancia nueva con qrcode habilitado."""
    try:
        payload = {
            "instanceName": INSTANCE_NAME,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
        }
        r = await client.post(
            f"{EVOLUTION_URL}/instance/create",
            json=payload,
            headers=HEADERS,
        )
        if r.status_code == 201:
            data = r.json()
            imprimir(f"Instancia creada: {data.get('instance', {}).get('instanceName', INSTANCE_NAME)}", "✓")
            return True
        else:
            imprimir(f"Error al crear instancia: {r.status_code} — {r.text[:200]}")
            return False
    except Exception as e:
        imprimir(f"Error al crear instancia: {e}")
        return False


async def obtener_qr_con_polling(client: httpx.AsyncClient) -> str | None:
    """
    Hace polling del endpoint /instance/connect hasta obtener el QR base64.

    En v2.1.1 el bug hace que count sea siempre 0 en el primer ciclo.
    La estrategia es: esperar a que Baileys genere el QR (puede tardar varios segundos)
    y reintentar. Si después de MAX_INTENTOS sigue sin QR, el bug está activo
    y hay que hacer el upgrade.
    """
    imprimir(f"Esperando QR (máx {MAX_INTENTOS * PAUSA_SEGS}s)...")
    print()

    for intento in range(1, MAX_INTENTOS + 1):
        try:
            r = await client.get(
                f"{EVOLUTION_URL}/instance/connect/{INSTANCE_NAME}",
                headers={"apikey": API_KEY},
                timeout=10.0,
            )

            if r.status_code != 200:
                imprimir(f"Intento {intento}/{MAX_INTENTOS}: status {r.status_code}")
                await asyncio.sleep(PAUSA_SEGS)
                continue

            data = r.json()

            # El endpoint devuelve: {count, code, base64, pairingCode}
            # 'code' = base64 PNG del QR
            # 'count' = número de QRs generados (0 = bug activo)
            code   = data.get("code")
            b64    = data.get("base64")
            count  = data.get("count", 0)

            qr_data = code or b64

            if qr_data and count > 0:
                print(f"\r  ✓ QR obtenido (intento {intento}, count={count})          ")
                return qr_data

            # Mostrar progreso
            status_text = f"count={count}" if count == 0 else f"count={count}, esperando imagen..."
            print(f"\r  Intento {intento:02d}/{MAX_INTENTOS} — {status_text}  ", end="", flush=True)

        except Exception as e:
            print(f"\r  Intento {intento:02d}/{MAX_INTENTOS} — error: {e}  ", end="", flush=True)

        await asyncio.sleep(PAUSA_SEGS)

    print()
    return None


async def main():
    print()
    print("=" * 60)
    print("  obtener_qr.py — Evolution API QR Code Extractor")
    print("=" * 60)
    print()
    imprimir(f"Servidor: {EVOLUTION_URL}")
    imprimir(f"Instancia: {INSTANCE_NAME}")
    print()

    async with httpx.AsyncClient(timeout=15.0) as client:

        # 1. Verificar que el servidor responde
        try:
            r = await client.get(EVOLUTION_URL, headers=HEADERS)
            info = r.json()
            version = info.get("version", "?")
            imprimir(f"Evolution API v{version} — servidor OK", "✓")
        except Exception as e:
            imprimir(f"No se puede conectar a {EVOLUTION_URL}: {e}", "✗")
            imprimir("Verifica que el servidor esté corriendo.")
            sys.exit(1)

        print()
        imprimir("Paso 1: Limpiando instancia anterior...")
        await borrar_instancia(client)
        await asyncio.sleep(2)

        imprimir("Paso 2: Creando instancia nueva...")
        if not await crear_instancia(client):
            imprimir("Fallo al crear instancia. Revisa los logs del servidor.", "✗")
            sys.exit(1)
        await asyncio.sleep(3)

        imprimir("Paso 3: Esperando QR...")
        qr_data = await obtener_qr_con_polling(client)

        if qr_data:
            print()
            imprimir("¡QR obtenido con éxito!", "✓")
            guardar_qr_html(qr_data)
            mostrar_qr_terminal(qr_data)
            print()
            print("  Para escanear:")
            print("  1. Abre el archivo qr.html en tu navegador")
            print("  2. En WhatsApp: Ajustes → Dispositivos vinculados → Vincular dispositivo")
            print("  3. Escanea el QR que aparece en la pantalla")
            print()
            imprimir("El QR expira en ~60 segundos. Si vence, ejecuta este script de nuevo.")
        else:
            print()
            imprimir("No se pudo obtener el QR después de todos los intentos.", "✗")
            print()
            print("  Esto confirma el bug de v2.1.1 (Issue #2385 en GitHub).")
            print()
            print("  SOLUCIÓN: Actualiza Evolution API a v2.2.3 o superior.")
            print("  Ejecuta este comando en el servidor (137.184.223.186):")
            print()
            print("    bash upgrade_evolution.sh")
            print()
            print("  O manualmente:")
            print("    docker compose pull evolution")
            print("    docker compose up -d evolution")
            print()
            print("  (Ver upgrade_evolution.sh para instrucciones detalladas)")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
