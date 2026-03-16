#!/usr/bin/with-contenv bashio

echo "Starting Lumberjacker..."
cd /app
exec python3 -m app.main
