---
from: gca
to: major-tom
date: 2026-03-15
subject: Integration Ready - Install Instructions
type: handoff
priority: normal
response: optional
---

# Integration Ready - Install Instructions

## What's Done

Ground Control custom integration is complete and pushed. It includes:

### Entities
**Sensors:**
- `sensor.ground_control_active_count`
- `sensor.ground_control_work_queue_count`
- `sensor.ground_control_total_open`
- `sensor.ground_control_completed_count`
- `sensor.ground_control_blocked_count`
- `sensor.ground_control_project_{slug}_status` (per project)
- `sensor.ground_control_project_{slug}_open_tasks` (per project)
- `sensor.ground_control_project_{slug}_progress` (per project)

**Binary Sensors:**
- `binary_sensor.ground_control_has_active`
- `binary_sensor.ground_control_has_blocked`

### Services
- `ground_control.create_task`
- `ground_control.update_task`
- `ground_control.move_task`
- `ground_control.complete_task`
- `ground_control.delete_task`
- `ground_control.create_project`
- `ground_control.update_project`
- `ground_control.archive_project`

## Installation

**User needs to:**

1. Pull the latest from ha-addons repo
2. Copy integration to custom_components:
   ```bash
   cp -r /path/to/ha-addons/ground-control/integration/ground_control /config/custom_components/
   ```
3. Restart Home Assistant
4. Go to Settings → Integrations → Add Integration → "Ground Control"
5. Enter addon URL: `http://localhost:8100` (or `http://192.168.6.8:8100`)

## Your Turn: Dashboards

You can now build HA dashboards using these entities. Example card:

```yaml
type: entities
title: Ground Control
entities:
  - entity: sensor.ground_control_active_count
  - entity: sensor.ground_control_work_queue_count
  - entity: sensor.ground_control_total_open
  - entity: binary_sensor.ground_control_has_blocked
```

Let me know if you run into any issues during installation or if you need any additional entities/services.

---

*Ground Control Agent (GCA) - ha-addons repo*
