"""Constants for Ground Control integration."""

DOMAIN = "ground_control"
DEFAULT_ADDON_URL = "http://localhost:8100"
CONF_ADDON_URL = "addon_url"

# Sensor keys
SENSOR_ACTIVE_COUNT = "active_count"
SENSOR_WORK_QUEUE_COUNT = "work_queue_count"
SENSOR_TOTAL_OPEN = "total_open"
SENSOR_COMPLETED_COUNT = "completed_count"
SENSOR_BLOCKED_COUNT = "blocked_count"

# Binary sensor keys
BINARY_HAS_ACTIVE = "has_active"
BINARY_HAS_BLOCKED = "has_blocked"

# Update interval in seconds
UPDATE_INTERVAL = 10
