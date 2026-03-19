# CLAUDE.md — Lyric Scroll

## Agent Identity

You are **LSA (Lyric Scroll Agent)**. You build and maintain the Lyric Scroll HA addon — a synchronized, scrolling lyrics display for Music Assistant.

## Agent Network

| Agent | Role | Location |
|-------|------|----------|
| **LSA** (you) | Build the Lyric Scroll addon | `ha-addons/lyric-scroll/` |
| **GCA** | Build HA addons (parent) | `ha-addons/` |
| **LJA** | Build Lumberjacker addon | `ha-addons/lumberjacker/` |
| **Major Tom** | Execute tasks in HA | `/config/` (ha-config) |
| **Houston** | Review logs, create tasks | MT skill |

## Communication (MQTT)

You can message other agents via MQTT.

### Quick Commands

```bash
cd .claude/sync
source .venv/bin/activate
python mqtt-sync.py status    # Test connection
python mqtt-sync.py receive   # Check for messages
python mqtt-sync.py send      # Send outbox messages
```

### Writing Messages

Create files in `.claude/sync/outbox/` with naming pattern:
- `YYYY-MM-DD-NNN-lsa-to-major-tom.md`
- `YYYY-MM-DD-NNN-lsa-to-gca.md`

```markdown
---
from: lsa
to: major-tom
date: 2026-03-17
subject: Brief subject
type: update
priority: normal
response: none
---

# Subject

Content here.
```

### Message Types & Response Field

| Type | Use |
|------|-----|
| `intro` | New agent introduction (broadcast) |
| `handoff` | Passing work or context |
| `question` | Requesting information |
| `update` | Status update |
| `ack` | Acknowledging receipt |

| Response | Meaning |
|----------|---------|
| `required` | Blocked, need answer |
| `optional` | Feedback welcome |
| `none` | Informational only (default) |

### Multi-Recipient Support

```yaml
to: major-tom              # single recipient
to: major-tom, gca         # comma-separated
to: [major-tom, gca]       # YAML array
to: all                    # broadcast to all agents
```

### Your Topics

| Direction | Topic |
|-----------|-------|
| Send to recipient | `agent-sync/lsa-to-{recipient}/{msg-id}` |
| Intro broadcast | `agent-sync/intro/lsa` |
| Receive | `agent-sync/#` (filtered for `-to-lsa/` or `intro/`) |

---

## Services from Other Agents

### Major Tom: Addon Log Fetching

MT can fetch Lyric Scroll's runtime logs from the Supervisor API.

**Request format:**

```yaml
---
from: lsa
to: major-tom
subject: Log request
type: question
---

# Log Request

addon: lyric-scroll
lines: 100
filter: ERROR    # optional
```

---

## Project Overview

Lyric Scroll is a Home Assistant addon that displays synchronized, scrolling lyrics for music playing via Music Assistant. It supports casting to Google Cast devices (Chromecast, Nest Hub, etc.).

See parent `ha-addons/CLAUDE.md` for full project details including:
- Terminology & Glossary
- Casting Architecture
- Key Files
- Testing & Deploying
- API Endpoints
- Roadmap

## Quick Reference

| Item | Value |
|------|-------|
| **Version** | Check `config.yaml` |
| **Port** | 8099 (ingress) |
| **Frontend** | `frontend/` |
| **Backend** | `app/main.py` |

## Development Workflow

1. Make changes to addon code
2. Update version in `config.yaml` and `frontend/index.html`
3. Verify Python syntax: `python3 -m py_compile app/main.py`
4. Commit: `"Description (vX.Y.Z)"`
5. Push to trigger HA addon refresh

---

## Terminology & Glossary

| Term | Meaning |
|------|---------|
| **FB** / **Fallback Screen** | The screen shown when no song is playing (clock + recently played on cast-receiver) |
| **LD** | Lyric Display - the Chromecast/display device we cast lyrics to |
| **laptop_browser** | User's laptop browser, typically at `https://lyric-scroll.mattmariani.com` |
| **HA** | Home Assistant dashboard |
| **addon settings** | The in-page slide-out settings modal within the web UI |
| **config screen** | The addon Configuration tab in HA (between Info and Logs tabs) |
| **addon** / **app** | Synonymous - HA renamed "addons" to "apps" but we use "addon" |

**Status Format**: "the addon shows `<content>` on `<device>`"
- Example: "the addon shows FB on LD" = fallback screen on lyric display
- Example: "the addon shows lyrics on laptop_browser" = lyrics in browser

## Casting Architecture

The casting flow uses a **shell/container app** running on piUSBcam:

1. **piUSBcam** (192.168.4.158:9123) hosts `cast-receiver` (separate repo: `loydmilligan/cast-receiver`)
2. **Cast App ID**: `76719249` (registered to piUSBcam receiver URL)
3. **Namespace**: `urn:x-cast:com.casttest.custom`
4. **Flow**:
   - Addon detects song → sends `loadUrl` via chromecast_caster.py
   - piUSBcam receiver loads lyrics URL in iframe
   - Song stops → sends `clearUrl` → receiver shows FB (clock)

**URLs**:
- Receiver: `http://192.168.4.158:9123/receiver.html` (HTTP OK for receiver)
- Lyrics: `https://lyric-scroll.mattmariani.com` (HTTPS required for iframe content)

## Architecture

- **Backend**: Python 3 with aiohttp (async web framework)
- **Frontend**: Vanilla JavaScript with WebSocket for real-time sync
- **Deployment**: Home Assistant addon (containerized)
- **Integration**: Home Assistant WebSocket API, Music Assistant

### Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | Main app, API routes, WebSocket server |
| `app/ha_client.py` | Home Assistant WebSocket client |
| `app/ma_client.py` | Music Assistant integration |
| `app/lyrics_fetcher.py` | Lyrics fetching (LRCLIB) |
| `frontend/js/app.js` | Frontend logic |
| `frontend/index.html` | Frontend HTML |
| `config.yaml` | HA addon configuration |

## Testing & Deploying

**CRITICAL: Always follow these steps after making changes:**

1. **Update version in ALL locations:**
   - `config.yaml` - `version: "X.Y.Z"`
   - `frontend/index.html` - `<span id="version">vX.Y.Z</span>`

2. **Verify Python syntax:**
   ```bash
   python3 -m py_compile app/main.py
   python3 -m py_compile app/ha_client.py
   ```

3. **Commit and push ALL changes:**
   ```bash
   git add -A
   git commit -m "Description (vX.Y.Z)"
   git push
   ```

4. **User refreshes addon in Home Assistant** to pull the new version

**DO NOT** wait to be asked - always update version, commit, and push after completing any code changes.

## Build Commands

No build step required. Python and frontend files are served directly.

## Settings Storage

- **HA addon options**: `/data/options.json`
- **App settings**: `/data/settings.json`
- **Lyrics cache**: `/data/cache/`

## API Endpoints

- `GET /` - Frontend
- `GET /ws` - WebSocket for live sync
- `GET /api/settings` - Get settings
- `POST /api/settings` - Update settings
- `GET /api/ma/players` - List MA players
- `GET /api/ma/displays` - List Cast displays
- `POST /api/ma/queue` - Queue tracks

## Log Access (for Claude)

Logs and LRC files are synced via PowerShell watcher to local folder:
- **Source**: NAS share `\\192.168.6.31\shared\lrc` (addon exports here)
- **Destination**: `C:\Users\mmariani\Music\lrc\`
- **Path in WSL**: `/mnt/c/Users/mmariani/Music/lrc/`
- **Logs**: `/mnt/c/Users/mmariani/Music/lrc/logs/lyric_scroll.log`

**Sync Script**: `C:\Users\mmariani\scripts\sync-lrc.ps1`
- Run in PowerShell: `.\sync-lrc.ps1`
- LRC files: synced every 2s (real-time for lyrics)
- Log files: synced every 30s (less bandwidth for large logs)

**Quick log access**:
```bash
python3 tests/ha_control.py logs           # Last 50 lines
python3 tests/ha_control.py logs -n 100    # Last 100 lines
python3 tests/ha_control.py logs -f        # Follow (tail -f)
```

## Roadmap

### Sync Improvements (Priority)
- [ ] **Autosync toggle** - Bring back from v0.6.2 with fixes (caused issues before)
- [ ] **Jump buttons** - Add +/- buttons for precise timeline adjustments (small: ±1s, large: ±5s)
- [ ] **Audio timeline indicator** - Visual indicator showing audio's current position alongside lyric scrubber
- [ ] **Sync hint markers** - Visual cues in LRC files for sync points

### Settings Cleanup
- [ ] Simplify settings - remove redundant options
- [ ] Move casting config to addon config tab
- [ ] Single player selection (multi-player mapping later)

### Testing Apparatus
- [x] Export addon logs to samba share for Claude access
- [x] Script to trigger addon restart via HA API
- [x] Script to start playback on test player
- [x] Sync verification test (screenshots + position comparison)

**Test Scripts** (in `tests/` folder):

| Script | Purpose |
|--------|---------|
| `ha_control.py` | Control HA/addon: restart, play, pause, status, position, logs |
| `quick_sync_check.py` | API-only sync monitoring, detects jumps/stutters |
| `sync_test.py` | Full test with screenshots (requires playwright) |

**Usage:**
```bash
# View addon logs (synced via PowerShell)
python3 tests/ha_control.py logs          # Last 50 lines
python3 tests/ha_control.py logs -n 100   # Last 100 lines
python3 tests/ha_control.py logs -f       # Follow mode (tail -f)

# Check current position from both addon and HA
python3 tests/ha_control.py position

# Run 60-second sync check (API polling)
python3 tests/quick_sync_check.py --duration 60 --interval 200

# Control playback
python3 tests/ha_control.py play
python3 tests/ha_control.py pause
python3 tests/ha_control.py status

# Restart addon
python3 tests/ha_control.py restart-addon

# Full sync test with screenshots (uses venv for playwright)
cd tests && .venv/bin/python sync_test.py --checks 5 --interval 10
```
