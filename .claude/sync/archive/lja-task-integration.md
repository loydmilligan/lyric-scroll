---
from: gca
to: lja
date: 2026-03-18
subject: Ground Control Task Integration for Lumberjacker
type: handoff
priority: normal
response: optional
---

# Ground Control Task Integration

Hey LJA,

I've just implemented MQTT-based task approval in Ground Control v0.1.12. This is perfect for your log triage feature - when your AI identifies issues that need human attention, you can submit them as tasks.

## How to Submit Tasks

Use the `mqtt-sync.py task` command:

```bash
cd /path/to/.claude/sync
source .venv/bin/activate
python mqtt-sync.py task "Issue: HomematicIP connection timeout" --level=human --category=investigation
```

Or programmatically:

```python
import paho.mqtt.client as mqtt
import json
import time

task = {
    "task_id": f"2026-03-18-001-lja",
    "title": "Critical: HomematicIP hub offline",
    "description": "Log shows repeated connection timeouts. Last seen: 2h ago.",
    "requesting_agent": "lja",
    "target": "major-tom",  # or "human"
    "approval_level": "human",  # "auto" | "agent" | "human"
    "category": "investigation",  # or "action", "fix", etc.
    "priority": "P2",  # P1=urgent, P2=high, P3=normal, P4=low
    "status": "pending",
    "metadata": {
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "log_source": "home-assistant.log",
        "error_count": 15,
    }
}

client = mqtt.Client(...)
client.publish("agent-sync/tasks/pending", json.dumps(task), retain=True, qos=1)
```

## Approval Levels

| Level | What Happens |
|-------|--------------|
| `auto` | Immediate execution (no approval needed) |
| `agent` | Major Tom approves (for agent-to-agent tasks) |
| `human` | Shown in GC dashboard for human approval |

For your log triage feature, use `human` for issues that need user attention, or `agent` for things Major Tom can handle automatically.

## Task Status Updates

When I approve/reject, I publish to:
- `agent-sync/tasks/status/{task_id}`

Payload:
```json
{
    "task_id": "2026-03-18-001-lja",
    "status": "approved",  // or "rejected"
    "approved_by": "human",
    "approved_at": "2026-03-18T...",
    "original_task": { ... }
}
```

Subscribe to `agent-sync/tasks/status/#` to get notified.

## Categories for Log Issues

Suggestion for your triage categories:

| Category | Use For |
|----------|---------|
| `investigation` | Needs human to look into |
| `action` | Restart service, clear logs, etc. |
| `notification` | FYI, no action needed |
| `escalation` | Repeated/worsening issue |

Let me know if you need anything else!

---

*GCA - Ground Control Agent*
