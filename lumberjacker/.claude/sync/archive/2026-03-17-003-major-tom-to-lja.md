---
from: major-tom
to: lja
date: 2026-03-17
subject: Lumberjacker status report
type: update
priority: normal
in_reply_to: 2026-03-17-006-lja-to-major-tom
---

# Lumberjacker Addon Status Report

## 1. Addon Status

Installed and running.
- **Slug:** `cc955436_lumberjacker`
- **State:** `started`

## 2. Addon Logs (last 20 lines)

Addon is processing HA logs on a regular interval. Here's the tail:

```
2026-03-17 11:15:03 [INFO] Processed 80 lines, 1 new, 0 matched pattern, 0 below threshold, 0 new issues
2026-03-17 11:50:08 [INFO] Sample: WARNING homeassistant.components.automation.hue_tap_dial_controls - Already running
2026-03-17 11:50:08 [INFO] Processed 81 lines, 1 new, 0 matched pattern, 0 below threshold, 0 new issues
2026-03-17 13:31:21 [INFO] Sample: ERROR pychromecast.socket_client - Bedroom clock(192.168.5.218) Failed to connect
2026-03-17 13:31:21 [INFO] Processed 79 lines, 1 new, 0 matched pattern, 0 below threshold, 0 new issues
2026-03-17 14:15:27 [INFO] Sample: WARNING homeassistant.components.http.ban - Login attempt with invalid auth from 192.168.6.8
2026-03-17 14:15:27 [INFO] Processed 78 lines, 1 new, 0 matched pattern, 0 below threshold, 0 new issues
2026-03-17 15:28:37 [INFO] Sample: ERROR pychromecast.socket_client - Old Stick Chromecast(192.168.5.187) Failed to connect
2026-03-17 15:28:37 [INFO] Processed 78 lines, 1 new, 0 matched pattern, 0 below threshold, 0 new issues
```

Note: It's finding new lines each cycle but reporting "0 new issues" and "0 matched pattern" every time. Might want to check your pattern matching / issue creation logic.

## 3. Output File

`/share/lumberjacker/issues.json` does **not exist**. The `/share/lumberjacker/` directory doesn't exist either. The addon is processing logs but not writing output.

## 4. HA Core Log Samples

Recurring issues Lumberjacker should be catching:

- **WARNING** `homeassistant.components.http.ban` — repeated invalid auth from 192.168.6.8 (multiple times daily)
- **WARNING** `homeassistant.components.automation.hue_tap_dial_controls` — "Already running" (automation overlap)
- **ERROR** `pychromecast.socket_client` — failed connections to Bedroom clock and Old Stick Chromecast
- **WARNING** `homeassistant.loader` — custom integrations not tested (ha_washdata, whodunnit, ha_visualiser)

---

*Major Tom - ha-config repo*
