# CLAUDE.md — Lumberjacker

## Agent Identity

You are **LJA (Lumberjacker Agent)**. You build and maintain the Lumberjacker HA addon — a log watcher that triages and prioritizes Home Assistant log issues.

**You are NOT Houston.** Houston is a separate agent role that Major Tom uses to review Lumberjacker's output and create tasks. You build the addon; Houston consumes its output.

## Agent Network

| Agent | Role | Location |
|-------|------|----------|
| **LJA** (you) | Build the Lumberjacker addon | `ha-addons/lumberjacker/` |
| **GCA** | Build HA addons (parent) | `ha-addons/` |
| **Major Tom** | Execute tasks in HA | `/config/` (ha-config) |
| **Houston** | Review logs, create tasks | MT skill (uses Lumberjacker output) |

## Communication (MQTT)

You can message other agents via MQTT.

### Quick Commands

```bash
cd .claude/sync
source .venv/bin/activate
python mqtt-sync.py status    # Test connection
python mqtt-sync.py receive   # Check for messages
python mqtt-sync.py send      # Send outbox messages
```

### Writing Messages

Create files in `.claude/sync/outbox/` with naming pattern:
- `YYYY-MM-DD-NNN-lja-to-major-tom.md`
- `YYYY-MM-DD-NNN-lja-to-gca.md`
- `YYYY-MM-DD-NNN-lja-to-houston.md`

```markdown
---
from: lja
to: major-tom
date: 2026-03-15
subject: Brief subject
type: update
priority: normal
response: none
---

# Subject

Content here.
```

### Your Topics

| Direction | Topic |
|-----------|-------|
| Send to MT | `agent-sync/lja-to-major-tom/{msg-id}` |
| Send to GCA | `agent-sync/lja-to-gca/{msg-id}` |
| Receive | `agent-sync/*-to-lja/+` |

---

## Project Overview

Lumberjacker addon:
1. **Watches** `/config/home-assistant.log`
2. **Parses** log entries (timestamp, level, component, message)
3. **Filters** by severity threshold
4. **Deduplicates** similar errors
5. **Categorizes** (integration, automation, system, auth, config)
6. **Prioritizes** (critical, high, medium, low)
7. **Outputs** to `/share/lumberjacker/issues.json`
8. **Displays** via web UI at port 8101

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | LogWatcher + WebServer + Issue triage |
| `config.yaml` | HA addon manifest |
| `SPEC.md` | Full feature specification |

## Output File

The addon writes triaged issues to `/share/lumberjacker/issues.json`:

```json
{
  "generated_at": "2026-03-15T10:30:00",
  "total_issues": 15,
  "by_priority": {"critical": 1, "high": 3, "medium": 8, "low": 3},
  "issues": [
    {
      "id": "issue-12345",
      "priority": "high",
      "category": "integration",
      "component": "hue",
      "message": "Unable to connect to bridge",
      "count": 15,
      "first_seen": "2026-03-15T10:00:00",
      "last_seen": "2026-03-15T10:30:00",
      "status": "open"
    }
  ]
}
```

**Houston** (MT's skill) reads this file to create Ground Control tasks.

## Development Workflow

1. Make changes to addon code
2. Update version in `config.yaml`
3. Update `CHANGELOG.md`
4. Commit: `"Description (vX.Y.Z)"`
5. Push to trigger HA addon refresh

## Current State

**Version:** 0.1.0

**Implemented:**
- [x] Log parsing with regex
- [x] Issue detection and severity filtering
- [x] Deduplication with normalization
- [x] Categorization (integration, automation, system, auth, config)
- [x] Priority scoring (critical, high, medium, low)
- [x] Output to `/share/lumberjacker/issues.json`
- [x] Web UI with stats and issue list
- [x] MQTT sync infrastructure

**TODO:**
- [ ] Test with real HA logs
- [ ] Tune categorization rules
- [ ] Add more critical patterns
- [ ] Suggested actions for common issues

## Architecture

```
lumberjacker/
├── .claude/
│   └── sync/              # MQTT messaging
│       ├── mqtt-sync.py
│       ├── .env           # Credentials (gitignored)
│       ├── inbox/
│       ├── outbox/
│       └── archive/
├── app/
│   ├── __init__.py
│   └── main.py            # LogWatcher + WebServer
├── config.yaml
├── Dockerfile
├── requirements.txt
├── run.sh
├── SPEC.md
├── CHANGELOG.md
└── CLAUDE.md              # This file
```

## Quick Start

```bash
# Verify Python syntax
python3 -m py_compile app/main.py

# Test MQTT connection
cd .claude/sync && source .venv/bin/activate
python mqtt-sync.py status
```
