# Home Assistant API Reference for Testing

## Authentication
All HA API calls require: `Authorization: Bearer $HA_TOKEN`

The token is stored in `~/.zshrc` as `HA_TOKEN` environment variable.

## Base URLs
- **Home Assistant**: `http://192.168.6.8:8123`
- **Lyric Scroll Addon**: `https://lyric-scroll.mattmariani.com`

## Working Endpoints

### HA Core API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/` | GET | API status check |
| `/api/config` | GET | HA configuration |
| `/api/states/<entity_id>` | GET | Get specific entity state |
| `/api/services/<domain>/<service>` | POST | Call a service |

### Key Entities
- `media_player.office` - Sonos speaker (test playback device)
- `media_player.old_chromecast` - Chromecast display (cast target)
- `media_player.office_2` - MA version of office player

### Example Commands

**Get entity state:**
```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.6.8:8123/api/states/media_player.office"
```

**Play media:**
```bash
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.office"}' \
  "http://192.168.6.8:8123/api/services/media_player/media_play"
```

**Pause media:**
```bash
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.office"}' \
  "http://192.168.6.8:8123/api/services/media_player/media_pause"
```

## Lyric Scroll Addon API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Frontend UI |
| `/ws` | WS | WebSocket for live sync |
| `/api/settings` | GET | Get current settings |
| `/api/settings` | POST | Update settings |
| `/api/ma/players` | GET | List MA players |
| `/api/ma/displays` | GET | List Cast displays |

**Get addon settings:**
```bash
curl -s "https://lyric-scroll.mattmariani.com/api/settings"
```

## NOT Working (via external API)

| Endpoint | Issue |
|----------|-------|
| `/api/states` (list all) | 401 Unauthorized |
| `/api/services` (list all) | 401 Unauthorized |
| `/api/hassio/*` | Empty responses (deprecated/internal only) |
| `/api/logbook` | 401 Unauthorized |

**Note:** Supervisor/Hassio API endpoints are internal-only and not accessible externally. Addon logs must be accessed via HA UI or the manual download process.

## Testing Workflow Scripts

### Play/Pause Office Speaker
```bash
# Play
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.office"}' \
  "http://192.168.6.8:8123/api/services/media_player/media_play"

# Pause
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.office"}' \
  "http://192.168.6.8:8123/api/services/media_player/media_pause"
```

### Check Current Playback State
```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.6.8:8123/api/states/media_player.office" | python3 -m json.tool
```

---
*Last updated: 2026-03-14*
