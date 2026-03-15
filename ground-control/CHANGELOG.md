# Changelog

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
