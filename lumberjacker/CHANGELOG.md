# Changelog

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
