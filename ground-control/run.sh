#!/usr/bin/with-contenv bashio

# Read MQTT configuration from addon options
export MQTT_BROKER=$(bashio::config 'mqtt_broker')
export MQTT_PORT=$(bashio::config 'mqtt_port')
export MQTT_USER=$(bashio::config 'mqtt_user')
export MQTT_PASS=$(bashio::config 'mqtt_pass')

bashio::log.info "MQTT broker: ${MQTT_BROKER}:${MQTT_PORT}"

cd /app
python3 main.py
