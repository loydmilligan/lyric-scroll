---
from: gca
to: major-tom
date: 2026-03-15
subject: Integration Installed - Build Dashboard Now
type: handoff
priority: normal
response: optional
---

# Integration Installed - Build Dashboard Now

User has installed the Ground Control integration. **22 entities are now available.** Your turn to build the HA dashboard.

## Available Entities

### Count Sensors
```
sensor.ground_control_active_count
sensor.ground_control_work_queue_count
sensor.ground_control_total_open
sensor.ground_control_completed_count
sensor.ground_control_blocked_count
```

### Binary Sensors
```
binary_sensor.ground_control_has_active
binary_sensor.ground_control_has_blocked
```

### Project Sensors (per project)
For each project (reorg, motion-lighting, occupancy-music, notifications):
```
sensor.ground_control_project_{slug}_status
sensor.ground_control_project_{slug}_open_tasks
sensor.ground_control_project_{slug}_progress
```

## Dashboard Ideas

### 1. Summary Card
```yaml
type: entities
title: Ground Control
entities:
  - entity: sensor.ground_control_active_count
    name: Active
  - entity: sensor.ground_control_work_queue_count
    name: Work Queue
  - entity: sensor.ground_control_total_open
    name: Total Open
  - entity: sensor.ground_control_blocked_count
    name: Blocked
```

### 2. Status Glance
```yaml
type: glance
title: Task Status
entities:
  - entity: binary_sensor.ground_control_has_active
    name: Working
  - entity: binary_sensor.ground_control_has_blocked
    name: Blocked
  - entity: sensor.ground_control_completed_count
    name: Done
```

### 3. Project Progress Bars
```yaml
type: custom:bar-card
entities:
  - entity: sensor.ground_control_project_reorg_progress
    name: HA Reorganization
  - entity: sensor.ground_control_project_motion_lighting_progress
    name: Motion Lighting
```

### 4. Conditional Alert
```yaml
type: conditional
conditions:
  - entity: binary_sensor.ground_control_has_blocked
    state: "on"
card:
  type: markdown
  content: "⚠️ Tasks are blocked!"
```

### 5. Button to Open Ground Control
```yaml
type: button
name: Open Ground Control
icon: mdi:rocket-launch
tap_action:
  action: url
  url_path: /api/hassio_ingress/YOUR_INGRESS_ID/
```

Or direct URL:
```yaml
tap_action:
  action: url
  url_path: http://192.168.6.8:8100
```

## Services Available

You can also create buttons that call services:

```yaml
type: button
name: Quick Task
icon: mdi:plus
tap_action:
  action: call-service
  service: ground_control.create_task
  service_data:
    subject: "New task from dashboard"
    bucket: brainstorm
```

## Suggested Dashboard Layout

1. **Top row**: Summary glance card with key counts
2. **Middle**: Project progress bars
3. **Bottom**: Conditional alerts + button to open full UI

Let me know if you need any additional entities or have questions about the data.

---

*Ground Control Agent (GCA) - ha-addons repo*
