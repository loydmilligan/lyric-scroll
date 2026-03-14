# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lyric Scroll is a Home Assistant addon that displays synchronized, scrolling lyrics for music playing via Music Assistant. It supports casting to Google Cast devices (Chromecast, Nest Hub, etc.).

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
| `lyric-scroll/app/main.py` | Main app, API routes, WebSocket server |
| `lyric-scroll/app/ha_client.py` | Home Assistant WebSocket client |
| `lyric-scroll/app/ma_client.py` | Music Assistant integration |
| `lyric-scroll/app/lyrics_fetcher.py` | Lyrics fetching (LRCLIB) |
| `lyric-scroll/frontend/js/app.js` | Frontend logic |
| `lyric-scroll/frontend/index.html` | Frontend HTML |
| `lyric-scroll/config.yaml` | HA addon configuration |

## Testing & Deploying

**CRITICAL: Always follow these steps after making changes:**

1. **Update version in ALL locations:**
   - `lyric-scroll/config.yaml` - `version: "X.Y.Z"`
   - `lyric-scroll/frontend/index.html` - `<span id="version">vX.Y.Z</span>`

2. **Verify Python syntax:**
   ```bash
   python3 -m py_compile lyric-scroll/app/main.py
   python3 -m py_compile lyric-scroll/app/ha_client.py
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

Logs are exported via samba share to local laptop folder for Claude to access:
- **Source**: HA addon logs
- **Destination**: `C:\Users\mmariani\Music\lrc\` (same sync as LRC files)
- **Path in WSL**: `/mnt/c/Users/mmariani/Music/lrc/`

TODO: Set up log export similar to LRC export.

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
- [ ] Export addon logs to samba share for Claude access
- [ ] Script to trigger addon restart via HA API
- [ ] Script to start playback on test player
- [ ] Screenshot capability from lyric-scroll page
