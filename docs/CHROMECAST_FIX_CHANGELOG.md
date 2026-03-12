# Chromecast Fix Changelog

## Version: fix/chromecast-pychromecast branch

### Problem

The addon was using Home Assistant's built-in cast service (`cast.show_lovelace_view`) to cast URLs. This service expects a **Lovelace dashboard view path** (like `/lovelace/living-room`), not a full URL.

When passing a URL like `http://192.168.6.8:8099`, it failed with:
```
error: unable to find a view with path http://192.168.6.8:8099
```

### Solution

Replaced the HA cast service calls with direct **PyChromecast** connection. PyChromecast:
- Connects directly to Chromecast by IP address
- Launches our custom receiver app (ID: `76719249`)
- Sends `loadUrl` messages to display any URL in the receiver's iframe

### Changes Made

#### `lyric-scroll/app/main.py`

1. **Replaced `_autocast_to_display()` implementation** (lines 366-418)
   - Removed: `cast.show_lovelace_view` and `media_player.play_media` HA service calls
   - Added: PyChromecast direct connection via `self.caster.cast_url()`
   - Now checks `chromecast_ip` setting instead of relying on display mappings

2. **Removed duplicate `_autocast_lyrics()` call** (line 83)
   - `_autocast_to_display()` now handles all casting
   - Prevents double-casting

3. **Simplified settings requirements**
   - Required: `autocast_enabled`, `chromecast_ip`, `autocast_url`
   - Optional: `display_mappings` (only used to check if display is idle)
   - `cast_app_id` defaults to `76719249`

### Settings Required

| Setting | Value | Description |
|---------|-------|-------------|
| `autocast_enabled` | `true` | Enable autocasting |
| `chromecast_ip` | `192.168.5.187` | IP of your Chromecast |
| `autocast_url` | `http://192.168.6.8:8099` | Your addon's lyrics URL |
| `cast_app_id` | `76719249` | Cast app ID (default works) |

### Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Lyric Scroll   │         │   Chromecast    │         │  Cast Receiver  │
│     Addon       │         │    Device       │         │   (on Pi)       │
│                 │         │                 │         │                 │
│ PyChromecast ───┼────────►│ Launches app ───┼────────►│ Loads receiver  │
│ cast_url() ─────┼────────►│ loadUrl msg ────┼────────►│ iframe shows    │
│                 │         │                 │         │ addon URL       │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Testing

1. Set the required settings in the addon
2. Play music on a configured media player
3. Chromecast should display the lyrics page automatically

### Files Modified

- `lyric-scroll/app/main.py` - Fixed casting logic
- `docs/CHROMECAST_FIX_CHANGELOG.md` - This file
