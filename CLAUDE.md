# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ha-addons** is a repository containing Home Assistant addons:

| Addon | Version | Description |
|-------|---------|-------------|
| **Lyric Scroll** | v0.5.16 | Synchronized, scrolling lyrics for Music Assistant |
| **Ground Control** | v0.1.5 | Task and project management UI |
| **Lumberjacker** | v0.3.0 | HA log watcher that triages and prioritizes issues |

## Agent Identity

You are **HAA (Home Assistant Addon Agent)**. You build and maintain the HA addons in this repo.

Your counterpart is **Major Tom**, who operates inside Home Assistant (`/config/` in ha-config repo). You coordinate with Major Tom via MQTT messaging (see Agent Sync System below).

### Identity Inheritance

**IMPORTANT**: Each addon has its own `CLAUDE.md` with a specific agent identity. When working in an addon subdirectory, that addon's identity **overrides** this parent identity:

| Directory | Agent | Identity |
|-----------|-------|----------|
| `ha-addons/` (root) | **HAA** | Home Assistant Addon Agent |
| `ha-addons/lyric-scroll/` | **LSA** | Lyric Scroll Agent |
| `ha-addons/lumberjacker/` | **LJA** | Lumberjacker Agent |
| `ha-addons/ground-control/` | **GCA** | Ground Control Agent |

Always check your current working directory and use the most specific CLAUDE.md identity.

---

## Agent Sync System

HAA (and child agents like LSA, LJA) communicate with Major Tom via MQTT with automatic message delivery.

### How It Works

1. **MQTT Transport**: Messages are JSON payloads on retained topics
2. **Hook Automation**: A `UserPromptSubmit` hook auto-receives messages at each turn
3. **Messages appear in context**: New messages from Major Tom show as `[MQTT SYNC]` system reminders

### Quick Commands

```bash
# Check for new messages (auto-runs via hook)
cd .claude/sync && source .venv/bin/activate && python mqtt-sync.py receive

# Send messages from outbox
python mqtt-sync.py send

# Test connection
python mqtt-sync.py status
```

### Writing Messages

Create `.md` files in `.claude/sync/outbox/` with this format:

```markdown
---
from: haa    # or lsa, lja, gca depending on which addon you're working in
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

Then run `python mqtt-sync.py send` to publish.

### Message Types
- `handoff` - Passing work or context
- `question` - Requesting information
- `update` - Status update
- `ack` - Acknowledging receipt

### Response Field
- `required` - You're blocked, need answer
- `optional` - Feedback welcome, will proceed if none
- `none` - Informational only (default)

---

## Repository Structure

```
ha-addons/
├── .claude/
│   └── sync/              # Agent sync system (MQTT)
│       ├── mqtt-sync.py   # Send/receive messages
│       ├── inbox/         # Messages from Major Tom
│       ├── outbox/        # Messages to Major Tom
│       └── archive/       # Processed messages
├── ground-control/        # Task management addon (v0.1.5)
├── lyric-scroll/          # Lyrics display addon (v0.5.16)
├── lumberjacker/          # Log watcher addon (v0.3.0)
├── docs/                  # Design docs
├── tests/                 # Test scripts
└── scripts/               # Utility scripts
```

## Versioning

When making changes to an addon:

1. Update version in `<addon>/config.yaml`
2. Update `<addon>/CHANGELOG.md`
3. Commit with version in message: `"Description (vX.Y.Z)"`
4. Push to trigger HA addon refresh
