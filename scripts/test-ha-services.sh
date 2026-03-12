#!/bin/bash
# Deeper investigation of HA services and MA integration

HA_HOST="192.168.6.8"
HA_PORT="8123"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5NjUzNmFkMmQ1Yzg0ZjA4YjgyMWM3OGM0MDE4N2ZkZCIsImlhdCI6MTc3MzI2NTg4OCwiZXhwIjoyMDg4NjI1ODg4fQ.0ys5aUxTjk3XXSSVjADWyLzShMj2W0lGzQKmAfV3k6I"
BASE_URL="http://${HA_HOST}:${HA_PORT}"

echo "=== Investigating HA Services & MA ==="
echo ""

echo "1. All service domains..."
curl -s -X GET "${BASE_URL}/api/services" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq -r '.[].domain' 2>/dev/null | sort -u | head -30
echo ""

echo "2. Looking for music-related services..."
curl -s -X GET "${BASE_URL}/api/services" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq -r '.[].domain' 2>/dev/null | grep -iE 'music|mass|media|player'
echo ""

echo "3. Media player entities..."
curl -s -X GET "${BASE_URL}/api/states" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq -r '.[] | select(.entity_id | startswith("media_player")) | .entity_id' 2>/dev/null | head -20
echo ""

echo "4. All addons list..."
curl -s -X GET "${BASE_URL}/api/hassio/addons" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq -r '.data.addons[].name' 2>/dev/null 2>/dev/null | grep -iE 'music|assistant' || echo "(checking raw...)"
curl -s -X GET "${BASE_URL}/api/hassio/addons" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq '.data.addons[] | {name: .name, slug: .slug}' 2>/dev/null | head -40
echo ""

echo "5. Testing ingress session for MA addon..."
# First get the addon slug
ADDON_SLUG=$(curl -s -X GET "${BASE_URL}/api/hassio/addons" \
  -H "Authorization: Bearer ${HA_TOKEN}" | jq -r '.data.addons[] | select(.name | test("music"; "i")) | .slug' 2>/dev/null | head -1)

if [ -n "$ADDON_SLUG" ]; then
  echo "Found addon: $ADDON_SLUG"
  echo "Getting ingress info..."
  curl -s -X GET "${BASE_URL}/api/hassio/addons/${ADDON_SLUG}/info" \
    -H "Authorization: Bearer ${HA_TOKEN}" | jq '{ingress, ingress_entry, ingress_url}' 2>/dev/null
else
  echo "No Music addon found via jq, trying alternate..."
  curl -s -X GET "${BASE_URL}/api/hassio/addons" \
    -H "Authorization: Bearer ${HA_TOKEN}" 2>/dev/null | head -500
fi
echo ""

echo "=== Done ==="
