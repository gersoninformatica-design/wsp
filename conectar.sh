#!/bin/bash
# conectar.sh — Conecta Elara a WhatsApp
# Ejecutar en el servidor: bash conectar.sh

API="http://localhost:8080"
KEY="elara-prod-2026-xyz"
NOMBRE="elara"
NUMERO="56998965231"
WEBHOOK="http://wsp-elara-1:8000/webhook"

echo ""
echo "========================================"
echo "  Conectando Elara a WhatsApp"
echo "========================================"
echo ""

# Paso 1: Desconectar instancia si existe
echo "[1/4] Limpiando instancia anterior..."
curl -s -X DELETE "$API/instance/logout/$NOMBRE" \
  -H "apikey: $KEY" > /dev/null 2>&1
sleep 2
curl -s -X DELETE "$API/instance/delete/$NOMBRE" \
  -H "apikey: $KEY" > /dev/null 2>&1
sleep 2
echo "  OK"

# Paso 2: Crear instancia nueva con webhook
echo "[2/4] Creando instancia nueva..."
RESULT=$(curl -s -X POST "$API/instance/create" \
  -H "apikey: $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"instanceName\": \"$NOMBRE\",
    \"integration\": \"WHATSAPP-BAILEYS\",
    \"qrcode\": true,
    \"webhook\": {
      \"url\": \"$WEBHOOK\",
      \"webhookByEvents\": false,
      \"webhookBase64\": false,
      \"enabled\": true,
      \"events\": [\"MESSAGES_UPSERT\"]
    }
  }")
echo "  OK"
sleep 2

# Paso 3: Obtener pairing code
echo "[3/4] Obteniendo codigo de emparejamiento..."
echo ""
CODE=$(curl -s -X POST "$API/instance/connect/$NOMBRE" \
  -H "apikey: $KEY" \
  -H "Content-Type: application/json" \
  -d "{\"number\": \"$NUMERO\"}")
echo "  Respuesta: $CODE"
echo ""

# Paso 4: Instrucciones
echo "========================================"
echo "  INSTRUCCIONES"
echo "========================================"
echo ""
echo "  Si ves un codigo de 8 digitos arriba:"
echo "  1. Abre WhatsApp en tu celular"
echo "  2. Configuracion > Dispositivos vinculados"
echo "  3. Vincular dispositivo"
echo "  4. Toca 'Vincular con numero de telefono'"
echo "  5. Ingresa el codigo de 8 digitos"
echo ""
echo "  Si NO ves codigo, abre en tu navegador:"
echo "  http://137.184.223.186:8080/manager"
echo "  y conecta desde ahi."
echo ""
echo "========================================"
