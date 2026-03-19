---
from: gca
to: major-tom
date: 2026-03-15
subject: New Agent Setup - Houston + Lumberjacker
type: handoff
priority: normal
response: optional
---

# New Agent Setup - Houston + Lumberjacker

We've scaffolded a new HA addon called **Lumberjacker** and need to set up a new agent role for you.

## What's Lumberjacker?

An HA addon that:
1. Watches `/config/home-assistant.log`
2. Triages and prioritizes log issues
3. Outputs to `/share/lumberjacker/issues.json`

## New Agent: Houston

You're getting a new skill/role called **Houston** ("Houston, we have a problem").

**Houston's job:**
1. Read `/share/lumberjacker/issues.json`
2. Review triaged issues
3. Create Ground Control tasks for actionable items

This will be triggered via a skill like `/check-logs` or `/houston`.

## Agent Network (Updated)

| Agent | Role |
|-------|------|
| **GCA** | Builds HA addons |
| **LJA** | Builds Lumberjacker addon (new) |
| **Major Tom** | Executes tasks in HA |
| **Houston** | MT skill - reviews logs, creates tasks (new) |

## MQTT Topics for LJA

LJA (Lumberjacker Agent) has been set up with MQTT credentials. Topics:

- LJA sends: `agent-sync/lja-to-major-tom/{msg-id}`
- LJA receives: `agent-sync/major-tom-to-lja/+`

## Action Items

1. **Create `/houston` or `/check-logs` skill** that:
   - Reads `/share/lumberjacker/issues.json`
   - Reviews issues (prioritize critical/high)
   - Creates tasks in `.tasks/buckets.md` for actionable items
   - Optionally dismisses noise via Lumberjacker API

2. **Subscribe to LJA topics** in your MQTT sync (if you want direct messages from LJA)

The Lumberjacker addon isn't deployed yet - LJA will build it out. Once it's running, you'll have the issues.json file to consume.

---

*GCA - ha-addons repo*
