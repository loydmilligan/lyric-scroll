# Changelog

## 0.1.13

- Add MQTT configuration options (mqtt_broker, mqtt_port, mqtt_user, mqtt_pass)
- Fix "Not authorized" error by reading credentials from addon config
- Default broker changed to "core-mosquitto" for HA addon installs

## 0.1.12

- Add Agent Tasks tab for MQTT-based task approvals
- MQTT client subscribes to `agent-sync/tasks/pending`
- Approve/reject buttons publish status to `agent-sync/tasks/status/{task_id}`
- Real-time updates via WebSocket
- Badge shows pending task count

## 0.1.11

- History tab now defaults to newest first
- Add sort toggle button to switch between newest/oldest first

## 0.1.10

- Add version and tasks_path to /api/stats endpoint for HA integration

## 0.1.9

- Fix ingress by using relative paths for CSS, JS, and API calls
- WebSocket now uses pathname for ingress base path support
- Works both via HA ingress and direct port access

## 0.1.8

- Fix file watcher to detect atomic writes (temp+rename pattern)
- Add on_moved() handler for Claude's atomic file edits
- Improved logging for file watcher events

## 0.1.7

- Add detailed logging for file watcher debugging
- Log all file events (MODIFIED/CREATED/DELETED/MOVED)
- Log task counts and projects on reload
- Log API calls for debugging

## 0.1.6

- Add /api/stats endpoint for HA integration sensors
- Add project CRUD endpoints (POST/PUT/DELETE /api/projects)
- Completed tasks now include time (YYYY-MM-DD HH:MM)
- Parser handles both date-only and datetime formats

## 0.1.5

- Add direct port access (http://ha-ip:8100)
- Enable host_network for direct access
- Expose port 8100/tcp

## 0.1.4

- Debug logging for frontend file serving
- Better error message when frontend not found
- Force Docker image rebuild

## 0.1.3

- Extensive debug logging on startup
- Shows filesystem exploration (/, /config, /homeassistant, /share, /data)
- Shows directory contents when parsing
- Shows task counts during parsing
- Better error messages for troubleshooting

## 0.1.2

- Add version badge to UI header (hover shows tasks_path)
- Smarter path detection: checks buckets.md has real content (>100 bytes)
- Prioritize /homeassistant over /config for HA OS setups
- Add /api/version endpoint

## 0.1.1

- Auto-detect .tasks path (checks /config, /homeassistant, /share)
- Better logging for path detection issues
- Empty tasks_path option triggers auto-detection

## 0.1.0

- Initial release
- Kanban board UI for task management
- Parse and sync with .tasks/ markdown files
- Project view with progress tracking
- Completed tasks history
- File watching for external changes (Major Tom sync)
