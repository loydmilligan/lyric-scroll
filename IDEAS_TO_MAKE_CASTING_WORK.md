# Ideas to Make Casting Work

**Goal**: Cast the Home Assistant dashboard at `http://192.168.6.8:8123/dashboard-lyrics/music` to `media_player.old_chromecast`

## How to Test Success

After each casting attempt, check the state of `media_player.old_chromecast`:
```bash
curl -s -X GET "http://192.168.6.8:8123/api/states/media_player.old_chromecast" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json"
```

**Success criteria**:
- State should be `playing` or `idle` (not `off` or `unavailable`)
- `app_name` attribute should show something related to the cast (e.g., "Backdrop", "Home Assistant Cast", or similar)
- `media_content_id` or other attributes might reference the dashboard URL

---

## Attempt Log

### Attempt 1
**Date**: 2026-03-11
**Idea**: Use the `cast.show_lovelace_view` service directly via Home Assistant REST API

**Approach**:
Call the Home Assistant REST API to invoke the `cast.show_lovelace_view` service with the dashboard path and entity_id.

**Command**:
```bash
curl -X POST "http://192.168.6.8:8123/api/services/cast/show_lovelace_view" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.old_chromecast", "dashboard_path": "dashboard-lyrics", "view_path": "music"}'
```

**Status**: FAILED - Cast app loads but shows "not connected" red icon
**Result**:
- API call returned `[]` (expected for service calls)
- Chromecast state: `playing`, `app_name`: "Home Assistant Lovelace", `media_title`: "Lyrics: music"
- **Visual Result**: Shows "not connected" red icon in top-right corner
- **Root Cause**: The Lovelace Cast receiver app cannot authenticate back to Home Assistant
- This is a known issue with cast.show_lovelace_view - requires proper HA Cast configuration and the Cast device to be able to reach and authenticate with HA

---

### Attempt 2
**Date**: 2026-03-12
**Idea**: Cast a URL directly using pychromecast to web receiver, bypassing HA's Lovelace Cast app

**Approach**:
The problem with Attempt 1 is that HA's Lovelace Cast app requires authentication which isn't working. Instead, we can use the generic DashCast receiver which can display any URL without authentication. Using the `media_player.play_media` service with a properly formatted cast payload for DashCast.

**Command**:
```bash
curl -X POST "http://192.168.6.8:8123/api/services/media_player/play_media" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.old_chromecast", "media_content_type": "cast", "media_content_id": "{\"app_name\": \"dashcast\", \"media_id\": \"http://192.168.6.8:8123/dashboard-lyrics/music\", \"media_type\": \"url\"}"}'
```

**Status**: FAILED - DashCast app did not launch
**Result**:
- API call returned `[]` (expected for service calls)
- Chromecast state: Still shows "Home Assistant Lovelace" app from previous attempt
- `last_changed` timestamp did not update - indicates the new app never launched
- DashCast may not be available or the JSON format was incorrect

---

### Attempt 3
**Date**: 2026-03-12
**Idea**: Use catt (Cast All The Things) command-line tool to cast URL directly

**Approach**:
Use the `catt` Python tool which provides direct control over Chromecasts without going through Home Assistant's cast integration. This tool can cast URLs to the Default Media Receiver or use DashCast.

First, install catt if needed, then cast the URL directly.

**Status**: PENDING
**Result**: (to be filled in after attempt)

---
