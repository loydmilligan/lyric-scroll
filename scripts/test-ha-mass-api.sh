#!/bin/bash
# Test Home Assistant and Music Assistant API access

HA_HOST="192.168.6.8"
HA_PORT="8123"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5NjUzNmFkMmQ1Yzg0ZjA4YjgyMWM3OGM0MDE4N2ZkZCIsImlhdCI6MTc3MzI2NTg4OCwiZXhwIjoyMDg4NjI1ODg4fQ.0ys5aUxTjk3XXSSVjADWyLzShMj2W0lGzQKmAfV3k6I"
BASE_URL="http://${HA_HOST}:${HA_PORT}"

echo "=== Testing Home Assistant API ==="
echo ""

echo "1. Testing HA API connection..."
curl -s -X GET "${BASE_URL}/api/" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json"
echo ""

echo ""
echo "2. Listing available services (looking for mass.*)..."
curl -s -X GET "${BASE_URL}/api/services" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" | jq '[.[] | select(.domain == "mass")]' 2>/dev/null || \
curl -s -X GET "${BASE_URL}/api/services" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" | grep -o '"mass[^"]*"' | head -20
echo ""

echo ""
echo "3. Testing mass.search service..."
curl -s -X POST "${BASE_URL}/api/services/mass/search" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Daft Punk", "media_type": "artist", "limit": 1}'
echo ""

echo ""
echo "4. Getting Music Assistant addon info..."
curl -s -X GET "${BASE_URL}/api/hassio/addons" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" | jq '.data.addons[] | select(.name | test("music|Music"; "i")) | {name, slug, state}' 2>/dev/null
echo ""

echo ""
echo "5. Testing MA API with HA token (via direct call)..."
curl -s -X POST "http://${HA_HOST}:8095/api" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"command": "players/all"}'
echo ""

echo ""
echo "=== Done ==="
