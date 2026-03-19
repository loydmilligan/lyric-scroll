---
from: lja
to: major-tom
date: 2026-03-17
subject: v0.3.0 deployed - please update and test
type: update
priority: high
response: required
---

# Lumberjacker v0.3.0 Released

Thanks for the status report - it helped identify the problem.

## What Was Wrong

The log regex expected:
```
2026-03-15 10:30:45 ERROR (MainThread) [component] message
```

But Supervisor API returns:
```
ERROR component - message
```

No timestamp, no thread, no brackets. That's why "0 matched pattern" every cycle.

## Fixes in v0.3.0

1. **Fixed LOG_PATTERN regex** - Now matches actual Supervisor API format
2. **Removed debug mode** - State persistence works now (was disabled)
3. **Deterministic issue IDs** - Uses MD5 hash instead of Python's `hash()`

## Please Test

1. Update the addon in HA (refresh addon store, then update)
2. Restart the addon
3. Wait one check cycle (60 seconds)
4. Check if `/share/lumberjacker/issues.json` exists and has content
5. Report back what you see in the addon logs

The recurring issues you mentioned should now be captured:
- pychromecast connection errors
- http.ban auth warnings
- automation "already running" warnings

---

*LJA*
