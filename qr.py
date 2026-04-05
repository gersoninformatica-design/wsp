#!/usr/bin/env python3
"""
qr.py — Genera codigo QR de WhatsApp para Elara
Ejecutar: python3 qr.py
Luego abrir: http://137.184.223.186:9999
"""
import urllib.request
import urllib.error
import json
import time
import http.server
import threading

API = "http://localhost:8080"
KEY = "elara-prod-2026-xyz"
PORT = 9999

def api(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("apikey", KEY)
    req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())
    except Exception as e:
        return {"error": str(e)}

def main():
    print("\n=== Generando QR de WhatsApp para Elara ===\n")

    # Limpiar instancia
    print("[1/3] Limpiando instancia anterior...")
    api("DELETE", "/instance/logout/elara")
    time.sleep(1)
    api("DELETE", "/instance/delete/elara")
    time.sleep(2)

    # Crear instancia nueva (v1)
    print("[2/3] Creando instancia y obteniendo QR...")
    result = api("POST", "/instance/create", {
        "instanceName": "elara",
        "qrcode": True,
        "webhook": "http://wsp-elara-1:8000/webhook",
        "webhook_by_events": False,
        "events": ["MESSAGES_UPSERT"]
    })

    # En v1, el QR viene directamente en connect
    qr_base64 = None
    print("   Esperando QR (puede tardar 5-10 seg)...")
    for i in range(10):
        time.sleep(3)
        r2 = api("GET", "/instance/connect/elara")
        code = r2.get("base64") or r2.get("qrcode") or ""
        if code and "base64," in str(code):
            qr_base64 = code
            break
        print(f"   Intento {i+1}/10...")

    if not qr_base64:
        print("\n[ERROR] No se pudo obtener el QR.")
        print("   Respuesta recibida:", json.dumps(result, indent=2))
        return

    # Generar HTML
    print("[3/3] Generando pagina web con QR...")
    if not qr_base64.startswith("data:"):
        qr_base64 = "data:image/png;base64," + qr_base64

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elara — Conectar WhatsApp</title>
<style>
body{font-family:Arial,sans-serif;text-align:center;padding:40px;background:#f0f0f0}
.box{background:white;border-radius:16px;padding:40px;display:inline-block;box-shadow:0 4px 20px rgba(0,0,0,0.1)}
img{width:280px;height:280px}
h2{color:#128C7E;margin-bottom:8px}
p{color:#666;font-size:14px;margin:8px 0}
.steps{text-align:left;margin:20px auto;max-width:300px;background:#f8f8f8;padding:16px;border-radius:8px}
.steps li{margin:8px 0;color:#333;font-size:14px}
</style>
</head>
<body>
<div class="box">
<h2>Escanea este QR con WhatsApp</h2>
<img src="QR_PLACEHOLDER" alt="QR Code">
<div class="steps">
<ol>
<li>Abre WhatsApp en tu celular</li>
<li>Configuracion &rarr; Dispositivos vinculados</li>
<li>Vincular dispositivo</li>
<li>Escanea este codigo QR</li>
</ol>
</div>
<p>El QR expira en 60 segundos. Recarga la pagina si es necesario.</p>
</div>
</body>
</html>""".replace("QR_PLACEHOLDER", qr_base64)

    with open("/tmp/qr.html", "w") as f:
        f.write(html)

    # Servidor HTTP simple
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            with open("/tmp/qr.html", "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"\n{'='*45}")
    print(f"  ABRE ESTO EN TU NAVEGADOR:")
    print(f"  http://137.184.223.186:{PORT}")
    print(f"{'='*45}")
    print("  Escanea el QR con WhatsApp.")
    print("  Presiona Ctrl+C cuando termines.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServidor detenido.")

if __name__ == "__main__":
    main()
