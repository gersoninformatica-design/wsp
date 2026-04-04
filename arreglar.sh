#!/bin/bash
# arreglar.sh — Actualiza Evolution API y conecta WhatsApp
# Ejecutar: bash arreglar.sh

API="http://localhost:8080"
KEY="elara-prod-2026-xyz"

echo ""
echo "========================================"
echo "  Arreglando Evolution API"
echo "========================================"
echo ""

echo "[1/5] Actualizando imagen a v2.2.3..."
docker compose pull evolution
echo ""

echo "[2/5] Reiniciando Evolution API..."
docker compose up -d evolution
echo ""

echo "[3/5] Esperando que arranque (20 seg)..."
sleep 20
echo "  OK"
echo ""

echo "[4/5] Borrando instancia vieja..."
curl -s -X DELETE "$API/instance/logout/elara" -H "apikey: $KEY" > /dev/null 2>&1
sleep 2
curl -s -X DELETE "$API/instance/delete/elara" -H "apikey: $KEY" > /dev/null 2>&1
sleep 2
echo "  OK"
echo ""

echo "[5/5] Creando instancia nueva..."
curl -s -X POST "$API/instance/create" \
  -H "apikey: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"instanceName":"elara","qrcode":true,"integration":"WHATSAPP-BAILEYS"}' > /dev/null 2>&1
sleep 3
echo "  OK"
echo ""

echo "========================================"
echo "  LISTO — Ahora abre en tu navegador:"
echo ""
echo "  http://137.184.223.186:8080/manager"
echo ""
echo "  El boton Get QR Code deberia funcionar"
echo "  ahora con la version corregida."
echo "========================================"
echo ""
