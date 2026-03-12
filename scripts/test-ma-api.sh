#!/bin/bash
# Test Music Assistant API endpoints

MA_HOST="192.168.6.8"
MA_PORT="8095"
BASE_URL="http://${MA_HOST}:${MA_PORT}"

echo "=== Testing Music Assistant API ==="
echo "Base URL: $BASE_URL"
echo ""

# Test basic endpoints
echo "1. Testing root..."
curl -s -o /dev/null -w "GET /           -> HTTP %{http_code}\n" "$BASE_URL/"

echo "2. Testing /api..."
curl -s -o /dev/null -w "GET /api        -> HTTP %{http_code}\n" "$BASE_URL/api"

echo "3. Testing /ws (WebSocket upgrade check)..."
curl -s -o /dev/null -w "GET /ws         -> HTTP %{http_code}\n" "$BASE_URL/ws"

echo "4. Testing /info..."
curl -s -w "\nHTTP %{http_code}\n" "$BASE_URL/info" 2>/dev/null | head -20

echo ""
echo "5. Testing JSON-RPC style POST to /api..."
curl -s -X POST "$BASE_URL/api" \
  -H "Content-Type: application/json" \
  -d '{"command": "players/all"}' | head -50

echo ""
echo ""
echo "6. Testing /api/players..."
curl -s "$BASE_URL/api/players" | head -50

echo ""
echo ""
echo "7. Checking what's listening on port $MA_PORT..."
echo "(This shows if it's the right service)"
curl -s -I "$BASE_URL/" 2>/dev/null | head -5

echo ""
echo "=== Done ==="
echo ""
echo "If WebSocket is required, the n8n workflow will need adjustment."
echo "MA v2 primarily uses WebSocket at ws://${MA_HOST}:${MA_PORT}/ws"
