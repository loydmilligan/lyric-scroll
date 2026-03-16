# Lumberjacker — HA Log Triage System

## Overview

Lumberjacker watches Home Assistant logs, identifies real problems, and triages/prioritizes them for action. It filters out noise, groups related issues, and presents actionable items.

## Core Features

### 1. Log Watching
- Monitor `/config/home-assistant.log` (configurable)
- Tail new entries in real-time
- Track position to avoid re-processing

### 2. Issue Detection
- Parse log format: `YYYY-MM-DD HH:MM:SS.mmm LEVEL (COMPONENT) [MODULE] Message`
- Filter by severity: error, warning, info
- Identify patterns that indicate real problems vs. noise

### 3. Triage & Prioritization

| Priority | Criteria |
|----------|----------|
| **Critical** | Errors affecting core functionality (HA startup, database, automations failing) |
| **High** | Repeated errors, integration failures, auth issues |
| **Medium** | Warnings that may indicate future problems |
| **Low** | Informational, deprecation notices, one-off errors |

### 4. Deduplication
- Group similar errors (same component + similar message)
- Track occurrence count and time range
- Show "first seen" and "last seen"

### 5. Categorization

| Category | Examples |
|----------|----------|
| **Integration** | Device unavailable, API errors, connection timeouts |
| **Automation** | Script errors, trigger failures, condition errors |
| **System** | Memory, CPU, disk, database issues |
| **Auth** | Login failures, token expiry |
| **Config** | YAML errors, deprecated configs |

## API

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/api/issues` | GET | List triaged issues |
| `/api/issues/{id}` | GET | Issue details |
| `/api/issues/{id}/dismiss` | POST | Dismiss an issue |
| `/api/issues/{id}/action` | POST | Mark as actioned |
| `/api/stats` | GET | Summary statistics |
| `/api/health` | GET | Health check |

### Issue Schema

```json
{
  "id": "issue-001",
  "priority": "high",
  "category": "integration",
  "component": "hue",
  "message": "Unable to connect to bridge",
  "count": 15,
  "first_seen": "2026-03-15T10:00:00Z",
  "last_seen": "2026-03-15T14:30:00Z",
  "sample_entries": ["...", "..."],
  "status": "open",
  "suggested_action": "Check network connectivity to Hue bridge"
}
```

## Future: Major Tom Integration

Lumberjacker can communicate with Major Tom via MQTT to:
1. Send triaged issues for task creation
2. Receive acknowledgments when tasks are created
3. Auto-dismiss issues that have been addressed

### MT Skill (Future)
```
/check-logs — MT reviews Lumberjacker output and creates tasks for actionable issues
```

## UI Design

Simple, dark-themed dashboard:
- Summary cards (critical/high/medium/low counts)
- Issue list with filters (priority, category, status)
- Issue detail view with log samples
- Quick actions (dismiss, create task, mark resolved)

## Configuration

```yaml
log_path: "/config/home-assistant.log"
check_interval: 60  # seconds
severity_threshold: "warning"  # minimum level to capture
```
