# Agent Sync System

This directory enables coordination between Claude Code agents working on related projects.

## Registered Agents

| Agent ID | Location | Role |
|----------|----------|------|
| `gca` | `~/Projects/ha-addons/` | Ground Control Agent - builds the HA addons |
| `lj` | `~/Projects/ha-addons/lumberjacker/` | Lumberjacker Agent - builds the log triage addon |
| `major-tom` | `/config/` (ha-config repo) | Major Tom - executes tasks in Home Assistant |

## Transport: MQTT

Messages are delivered via MQTT with retained messages for offline delivery.

| Setting | Value |
|---------|-------|
| Broker | `192.168.4.158:1883` |
| GCA Send | `agent-sync/gca-to-major-tom/{msg-id}` |
| GCA Recv | `agent-sync/major-tom-to-gca/+` (wildcard) |
| MT Send | `agent-sync/major-tom-to-gca/{msg-id}` |
| MT Recv | `agent-sync/gca-to-major-tom/+` (wildcard) |
| LJ Send | `agent-sync/lj-to-major-tom/{msg-id}` or `agent-sync/lj-to-gca/{msg-id}` |
| LJ Recv | `agent-sync/major-tom-to-lj/+` or `agent-sync/gca-to-lj/+` |

### Scripts

- `mqtt-sync.py send` - Publish all messages from `outbox/`
- `mqtt-sync.py receive` - Fetch messages to `inbox/`
- `mqtt-sync.py status` - Test connection

### Hook Automation

GCA has a hook in `~/.claude/hooks/mqtt_sync_hook.py` that runs on `UserPromptSubmit` and `Stop` events. It auto-receives messages and injects them into context as `[MQTT SYNC]` system reminders.

Major Tom has a similar hook in `/config/.claude/hooks/mqtt_sync_hook.py`.

## Communication Protocol

Agents communicate via markdown files in their respective `.claude/sync/` directories.

### File Format

```
YYYY-MM-DD-HHMMSS-{from}-to-{to}.md
```

Example: `2026-03-15-143022-gca-to-major-tom.md`

### Message Structure

```markdown
---
from: gca
to: major-tom
date: 2026-03-15T14:30:22
subject: Brief subject line
type: handoff | question | update | ack
priority: normal | urgent
response: required | optional | none
---

# Subject Line

Message content here.

## Action Items (if any)

- [ ] Item 1
- [ ] Item 2
```

### Message Types

- **handoff**: Passing work or context to the other agent
- **question**: Requesting information or clarification
- **update**: Status update, no action required
- **ack**: Acknowledging receipt

### Response Field

- **required**: You need information or a decision before you can proceed
- **optional**: You'd welcome feedback but will proceed with your stated approach if none comes
- **none**: Informational only — assume message was accepted

**Guidance (not rules):**

Use `required` sparingly — only when you're actually blocked:
- Questions that need answers before work continues
- Decisions between options you can't make alone
- Blockers that need the other agent's action

Use `none` as the default. Silence means acceptance. Don't respond just to acknowledge — respond when you have something to add, disagree with, or need to clarify.

You can always respond to a `none` message if you have concerns or questions. The field signals sender intent, not recipient permissions. of a message

## Workflow

### GCA (ha-addons repo)
1. Hook auto-receives messages on each user prompt
2. New messages appear in context as `[MQTT SYNC]` reminders
3. Write responses to `outbox/`, run `mqtt-sync.py send`
4. Archive processed inbox messages to `archive/`

### Major Tom (ha-config repo)
1. Hook auto-receives messages on each user prompt
2. New messages appear in context as `[MQTT SYNC]` reminders
3. Write responses to `outbox/`, run `mqtt-sync.py send`
4. Archive processed inbox messages to `archive/`

## Directory Structure

```
.claude/sync/
├── README.md          # This file
├── inbox/             # Messages TO this agent
├── outbox/            # Messages FROM this agent
└── archive/           # Processed messages
```
