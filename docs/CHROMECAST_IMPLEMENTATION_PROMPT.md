# Chromecast Integration Implementation Prompt

Use this prompt to instruct the lyric-scroll building agent to implement Chromecast casting.

---

## Prompt

Implement automatic Chromecast casting for the lyric-scroll addon using the approach documented in `@docs/CHROMECAST_INTEGRATION_GUIDE.md`.

### Summary

A custom Chromecast receiver is already deployed and running at `http://192.168.4.158:9123/receiver.html`. The receiver displays any URL sent to it in an iframe. Your task is to integrate PyChromecast into the addon backend to automatically cast the lyrics page when music starts playing.

### What's Already Done

1. **Cast Developer Account** - Registered with App ID `76719249`
2. **Custom Receiver** - Deployed on Docker at `http://192.168.4.158:9123/receiver.html`
3. **Test Chromecast** - "Old Chromecast" at `192.168.5.187` registered as test device
4. **PyChromecast Module** - `chromecast_caster.py` ready to use

### What You Need to Implement

1. **Add PyChromecast dependency** to the addon requirements
2. **Copy/adapt `chromecast_caster.py`** into the addon
3. **Create a Chromecast service** that:
   - Connects to configured Chromecast IP on startup
   - Launches the custom receiver app
   - Exposes `cast_url(url)` method for other services to call
4. **Integrate with media player events**:
   - When a song starts playing → `cast_url(lyrics_page_url)`
   - When playback stops → `clear_content()`
5. **Add addon configuration** for:
   - `chromecast_ip` - IP address of target Chromecast
   - `cast_app_id` - Default to `76719249`

### Key Configuration Values

| Setting | Value |
|---------|-------|
| App ID | `76719249` |
| Namespace | `urn:x-cast:com.casttest.custom` |
| Receiver URL | `http://192.168.4.158:9123/receiver.html` |
| Test Chromecast IP | `192.168.5.187` |

### Message Protocol

Send JSON to the receiver:
- `{"loadUrl": "http://your-ha:port/lyrics/song123"}` - Display lyrics page
- `{"clearUrl": true}` - Clear and show standby
- `{"message": "text"}` - Show text message

### Important Notes

1. **Use IP addresses, not hostnames** - Chromecast needs direct IP access
2. **URLs must be LAN-accessible** - The lyrics page URL must be reachable from the Chromecast
3. **Receiver is already deployed** - You don't need to deploy or modify the receiver
4. **No browser needed** - PyChromecast works from Python backend, fully automatic

### Reference

Full documentation: `@docs/CHROMECAST_INTEGRATION_GUIDE.md`
Python module example: `chromecast_caster.py` (in project root)
