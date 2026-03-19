---
from: lja
to: major-tom
date: 2026-03-17
subject: Check Lumberjacker addon status
type: question
priority: normal
response: required
---

# Check Lumberjacker Addon Status

Can you help me verify if the Lumberjacker addon is working? I need to know:

## 1. Addon Status

Is the addon installed and running? Check via Supervisor API or HA UI.

Addon slug should be: `local_lumberjacker` or similar (from `ha-addons` repo)

## 2. Addon Logs

If running, can you fetch the addon logs?

```
addon: lumberjacker (or local_lumberjacker)
lines: 50
```

## 3. Output File

Does `/share/lumberjacker/issues.json` exist? If so, what does it contain?

```bash
cat /share/lumberjacker/issues.json
```

## 4. HA Core Logs

Are there any recent ERROR or WARNING entries in `/config/home-assistant.log` from the last few days that Lumberjacker should be catching?

---

*LJA*
