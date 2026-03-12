# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lyric Scroll is a Home Assistant addon that displays synchronized, scrolling lyrics for music playing via Music Assistant. It supports casting to Google Cast devices (Chromecast, Nest Hub, etc.).

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
