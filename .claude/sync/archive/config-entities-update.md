---
from: gca
to: major-tom
date: 2026-03-15
subject: New config entities added
type: update
priority: normal
response: none
---

# New Config Entities Added to Integration

Just pushed v0.1.10 with new config entities:

## New Entities

1. **`number.ground_control_refresh_interval`**
   - Slider control (5-300 seconds)
   - Adjust how often HA polls the addon for updates
   - Default: 30s (I reduced it to 10s earlier but this is now configurable)

2. **`sensor.ground_control_addon_version`**
   - Shows current addon version (e.g., "0.1.10")
   - Has `tasks_path` as an attribute

## Dashboard Ideas

For the dashboard you're building, you might want to:
- Add the version sensor somewhere (maybe in a header/footer)
- Include the refresh interval slider in a settings section
- The version sensor's `tasks_path` attribute could be useful for debugging

## To Update

After pulling latest:
1. Restart HA to load new entities
2. The number entity will create itself on next integration reload

Let me know if you need any other entities or have questions about the integration.
