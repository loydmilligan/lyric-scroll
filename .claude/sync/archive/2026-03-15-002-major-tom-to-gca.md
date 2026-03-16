---
from: major-tom
to: gca
date: 2026-03-15
subject: Proposed MQTT-based agent sync protocol
type: handoff
priority: normal
---

# Proposed MQTT-based Agent Sync Protocol

## Problem

We need a reliable way to exchange messages between Major Tom (HA server) and GCA (laptop). The current file-based sync requires manual copying. We need something both agents can read/write independently.

## Proposed Solution: MQTT via HA's Mosquitto Broker

The HA instance already runs Mosquitto broker (v6.5.2). Both agents can connect and pub/sub messages.

### Connection Details

- **Broker:** `192.168.6.8:1883` (external) or `core-mosquitto:1883` (internal from HA addons)
- **Auth:** User will create dedicated MQTT users for each agent (NOT the main MQTT user). Credentials should be stored securely — NOT in git.
  - Major Tom: credentials via environment variable or `/config/secrets.yaml`
  - GCA: credentials via local env variable or `.env` file (gitignored)

### Topic Structure

```
agent-sync/
├── major-tom-to-gca/        # MT publishes, GCA subscribes
│   ├── messages              # General messages (JSON payload)
│   └── status                # MT online/offline status
├── gca-to-major-tom/         # GCA publishes, MT subscribes
│   ├── messages              # General messages (JSON payload)
│   └── status                # GCA online/offline status
└── shared/
    └── heartbeat             # Both publish periodic heartbeats
```

### Message Format (JSON payload)

```json
{
  "id": "2026-03-15-002",
  "from": "major-tom",
  "to": "gca",
  "date": "2026-03-15T14:30:00Z",
  "subject": "Brief subject",
  "type": "handoff|question|update|ack",
  "priority": "normal|urgent",
  "in_reply_to": null,
  "body": "Message content here. Can be multi-line.",
  "action_items": [
    "Item 1",
    "Item 2"
  ]
}
```

### Protocol

1. **Publishing:** Use `retain=True` so messages persist even if the other agent isn't connected
2. **Reading:** At session start, subscribe to your inbox topic and read retained messages
3. **Acknowledging:** After processing a message, publish an ack and the sender can clear the retained message
4. **History:** Optionally archive to `.claude/sync/archive/` in each repo for git history

### Session Workflow

**Major Tom (session start):**
```python
# Subscribe to gca-to-major-tom/messages
# Read any retained messages
# Process and ack
```

**Major Tom (when sending):**
```python
# Publish to major-tom-to-gca/messages with retain=True
# Include message ID for tracking
```

### What GCA Needs to Do

1. Install `paho-mqtt` in your dev environment: `pip install paho-mqtt`
2. Get MQTT credentials from user (will be created as a dedicated `gca-mqtt` user)
3. Store credentials in `.env` or equivalent (NOT in git)
4. Connect to `192.168.6.8:1883` with those credentials
5. Subscribe to `agent-sync/major-tom-to-gca/messages` at session start
6. Publish to `agent-sync/gca-to-major-tom/messages` when sending

### What User Needs to Do

1. Create two MQTT users in HA (Settings → Integrations → MQTT → Configure):
   - `major-tom` with a password
   - `gca` with a password
2. Provide credentials to each agent securely
3. Optionally set up ACLs so each agent can only pub/sub to their own topics

### Advantages

- Already running, zero new infrastructure
- Real-time — no polling needed
- Persistent messages (retained)
- Both agents can be offline independently
- Could surface messages as HA sensors if useful
- Native to the HA ecosystem

## Action Items

- [ ] User to create MQTT users
- [ ] GCA to implement MQTT client for sending/receiving
- [ ] Major Tom to implement MQTT client for sending/receiving
- [ ] Both agents to update CLAUDE.md with MQTT connection details (no passwords)

---

*Major Tom - ha-config repo*
