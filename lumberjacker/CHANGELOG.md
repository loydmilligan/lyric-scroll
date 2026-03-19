# Changelog

## 0.4.5

- Added "Generate Test Issues" button for testing AI triage
  - Creates 5 realistic fake issues (hue, zwave, mqtt, automation, core)
  - Issues are untriaged so they get picked up by AI triage

## 0.4.4

- Issues now persist across addon restarts
  - Loads issues from `issues.json` on startup
  - Preserves counts, AI triage status, and dismissed state
- Added "Run AI Triage" button to web UI
  - Only shows when AI triage is enabled
  - Shows feedback on completion (issues triaged count)

## 0.4.3

- Fix AI triage timing bug: initial delay now waits for first watcher cycle
  - Changed from fixed 30s to `check_interval + 10s` buffer (~70s default)
  - Ensures issues are detected before first triage runs
- Improve AI triage logging visibility
  - "No untriaged issues, skipping" now logs at INFO level (was DEBUG)
  - Added "Checking for untriaged issues..." log before each check

## 0.4.2

- Run AI triage 30 seconds after startup instead of waiting full interval
  - Better for testing and immediate feedback on new issues

## 0.4.1

- Fix empty error message in AI triage failure logging
  - Now logs exception type and full traceback for debugging
- Fix KeyError/IndexError when OpenRouter returns unexpected response structure
  - Gracefully handles malformed API responses

## 0.4.0

### AI Triage Integration

- **NEW**: OpenRouter AI integration for intelligent issue triage
  - Analyzes log issues to determine actionability
  - Creates tasks for Major Tom via MQTT
  - Configurable triage interval (default: 60 minutes)
  - Manual triage trigger via `/api/triage` endpoint

- **NEW**: MQTT task publishing to Ground Control
  - Publishes tasks to `agent-sync/tasks/pending`
  - Supports approval levels: `auto`, `agent`, `human`
  - Task categories: `investigation`, `action`, `notification`, `escalation`

### New Config Options

- `ai_triage_enabled`: Enable/disable AI triage (default: false)
- `openrouter_api_key`: API key for OpenRouter
- `openrouter_model`: Model to use (default: `anthropic/claude-3-haiku`)
- `triage_interval`: Minutes between triage runs (default: 60)
- `mqtt_broker`: MQTT broker hostname
- `mqtt_port`: MQTT broker port (default: 1883)
- `mqtt_user`: MQTT username
- `mqtt_password`: MQTT password

### Issue Enhancements

- Added AI triage fields to issues:
  - `task_id`: ID of created task (if any)
  - `ai_triaged_at`: Timestamp of last AI analysis
  - `ai_actionable`: Whether AI determined issue is actionable
  - `ai_suggested_action`: AI-suggested action to take

### API Endpoints

- `POST /api/triage`: Manually trigger AI triage
- `GET /api/triage/status`: Get AI triage status

## 0.3.2

- Strip ANSI color codes from Supervisor API log output
  - Color codes at start of lines were breaking regex pattern matching

## 0.3.1

- Fix log pattern regex to match actual HA log format with timestamps
  - Format: `2026-03-18 04:41:54.627 ERROR (Thread-22) [component] message`
  - Previous regex expected `ERROR component - message` which doesn't match

## 0.3.0

- **BREAKING**: Fix log pattern regex to match actual Supervisor API format
  - Old: `TIMESTAMP LEVEL (Thread) [component] message`
  - New: `LEVEL component - message`
- Remove debug mode that was preventing state persistence
- Fix issue ID generation to use deterministic MD5 hash (consistent across restarts)
- Issues now properly persist and deduplicate across addon restarts

## 0.2.3

- DEBUG: Log sample lines at INFO level to see actual log format
- DEBUG: Start with fresh state (ignores cache) to ensure we see log samples
- This is a diagnostic release to identify log format issues

## 0.2.2

- Fix log pattern regex to handle optional milliseconds and flexible whitespace
- Add detailed logging: matched lines, severity filtered, etc.

## 0.2.1

- Add `hassio_role: homeassistant` to fix 403 error on Supervisor API

## 0.2.0

- Switch from file-based log reading to Supervisor API
- No longer requires log file to exist on disk
- Add "Refresh Now" button to UI
- Show last updated timestamp in UI
- Track processed lines by hash to avoid re-processing
- Remove log_path config option (now uses API)

## 0.1.1

- Add debug logging to diagnose log file path issues
- Check multiple potential log locations at startup

## 0.1.0

- Initial scaffolding
- Log file watching infrastructure
- Triage and prioritization framework
- Web UI for viewing triaged issues
