# Lyric Scroll API Documentation

This document describes the API endpoints available in Lyric Scroll for programmatic control of Music Assistant playback. These endpoints are designed for AI assistants and automation systems to queue music and manage playback.

## Base URL

```
http://192.168.6.8:8099
```

## Authentication

No authentication required for local network access.

---

## Endpoints

### Queue Multiple Tracks

Queue a playlist of tracks on a Music Assistant player. This is the primary endpoint for AI playlist creation.

**Endpoint:** `POST /api/ma/queue`

**Request Body:**
```json
{
  "entity_id": "media_player.office_2",
  "tracks": [
    "Daft Punk - One More Time",
    "Queen - Bohemian Rhapsody",
    "Radiohead - Karma Police"
  ],
  "enqueue": "play"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity_id` | string | No* | Music Assistant player entity ID. Must end in `_2` (e.g., `media_player.office_2`). *Required if no default player is configured. |
| `tracks` | array | Yes | List of track queries. Format: "Artist - Song Title" works best. Can also be just song titles. |
| `enqueue` | string | No | Queue behavior: `play` (default, replaces queue), `add` (append to queue), `next` (play after current track) |

**Response:**
```json
{
  "success": true,
  "entity_id": "media_player.office_2",
  "added_count": 3,
  "missing_count": 0,
  "added": [
    {
      "query": "Daft Punk - One More Time",
      "uri": "spotify--abc123://track/xyz",
      "name": "One More Time",
      "artist": "Daft Punk"
    }
  ],
  "missing": []
}
```

**Example - Queue a workout playlist:**
```bash
curl -X POST http://192.168.6.8:8099/api/ma/queue \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "media_player.office_2",
    "tracks": [
      "Survivor - Eye of the Tiger",
      "Kanye West - Stronger",
      "Eminem - Lose Yourself"
    ],
    "enqueue": "play"
  }'
```

---

### Play Single Track

Play a specific track by its Music Assistant URI.

**Endpoint:** `POST /api/ma/play`

**Request Body:**
```json
{
  "entity_id": "media_player.office_2",
  "media_id": "spotify--abc123://track/xyz",
  "media_type": "track",
  "enqueue": "play"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity_id` | string | No* | Music Assistant player entity ID |
| `media_id` | string | Yes | Track URI from Music Assistant (obtained from search) |
| `media_type` | string | No | Type of media: `track`, `album`, `playlist`, `artist` (default: `track`) |
| `enqueue` | string | No | Queue behavior: `play`, `add`, `next` |

---

### Search for Tracks

Search Music Assistant for tracks, albums, artists, or playlists.

**Endpoint:** `POST /api/ma/search`

**Request Body:**
```json
{
  "query": "Bohemian Rhapsody",
  "media_types": ["track"],
  "limit": 5
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `media_types` | array | No | Types to search: `track`, `album`, `artist`, `playlist` (default: `["track"]`) |
| `limit` | integer | No | Max results (default: 5) |

**Response:**
```json
{
  "tracks": [
    {
      "uri": "spotify--abc123://track/xyz",
      "name": "Bohemian Rhapsody",
      "artists": [{"name": "Queen"}],
      "album": {"name": "A Night At The Opera"}
    }
  ],
  "albums": [],
  "artists": [],
  "playlists": []
}
```

---

### List Available Players

Get all Music Assistant players that can be used for playback.

**Endpoint:** `GET /api/ma/players`

**Response:**
```json
{
  "players": [
    {
      "entity_id": "media_player.office_2",
      "friendly_name": "Office",
      "state": "idle",
      "mass_player_type": "player"
    },
    {
      "entity_id": "media_player.kitchen_nest_2",
      "friendly_name": "Kitchen Nest",
      "state": "off",
      "mass_player_type": "player"
    }
  ]
}
```

**Note:** Only use players with `_2` suffix - these are Music Assistant wrapped players.

---

### List Available Displays

Get all Cast displays that can show lyrics.

**Endpoint:** `GET /api/ma/displays`

**Response:**
```json
{
  "displays": [
    {
      "entity_id": "media_player.living_room_tv",
      "friendly_name": "Living Room TV",
      "state": "off",
      "device_class": "tv"
    }
  ]
}
```

---

### Get Settings

Retrieve current Lyric Scroll settings.

**Endpoint:** `GET /api/settings`

**Response:**
```json
{
  "ma_players": ["media_player.office_2", "media_player.kitchen_nest_2"],
  "default_player": "media_player.office_2",
  "display_mappings": {
    "media_player.office_2": "media_player.office_display"
  }
}
```

---

### Update Settings

Update Lyric Scroll settings.

**Endpoint:** `POST /api/settings`

**Request Body:**
```json
{
  "ma_players": ["media_player.office_2"],
  "default_player": "media_player.office_2",
  "display_mappings": {
    "media_player.office_2": "media_player.office_display"
  }
}
```

---

## Common Use Cases

### 1. AI Creates a Mood-Based Playlist

```bash
curl -X POST http://192.168.6.8:8099/api/ma/queue \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "media_player.living_room_2",
    "tracks": [
      "Norah Jones - Come Away With Me",
      "Jack Johnson - Better Together",
      "John Mayer - Gravity",
      "Adele - Make You Feel My Love",
      "Ed Sheeran - Thinking Out Loud"
    ],
    "enqueue": "play"
  }'
```

### 2. Add Songs to Current Queue

```bash
curl -X POST http://192.168.6.8:8099/api/ma/queue \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "media_player.office_2",
    "tracks": ["The Beatles - Here Comes The Sun"],
    "enqueue": "add"
  }'
```

### 3. Play Next (Skip Queue)

```bash
curl -X POST http://192.168.6.8:8099/api/ma/queue \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "media_player.office_2",
    "tracks": ["Rick Astley - Never Gonna Give You Up"],
    "enqueue": "next"
  }'
```

### 4. Search Before Playing

```bash
# First search
curl -X POST http://192.168.6.8:8099/api/ma/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Taylor Swift Anti-Hero", "limit": 1}'

# Then play using the URI from search results
curl -X POST http://192.168.6.8:8099/api/ma/play \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "media_player.office_2",
    "media_id": "spotify--abc://track/xyz",
    "enqueue": "play"
  }'
```

---

## Tips for AI Integration

1. **Track format:** "Artist - Song Title" gives best search results
2. **Use `_2` suffix:** Always use player entities ending in `_2` (Music Assistant versions)
3. **Check response:** The `missing` array shows tracks that couldn't be found
4. **Default player:** If `default_player` is configured, `entity_id` can be omitted
5. **Enqueue modes:**
   - `play` - Replace current queue and start playing
   - `add` - Append to end of current queue
   - `next` - Insert after currently playing track

---

## Error Handling

**400 Bad Request:**
```json
{"error": "entity_id required (or set default_player in settings)"}
```

**500 Internal Server Error:**
```json
{"error": "Music Assistant not configured"}
```

Always check the response `success` field and `missing` array to handle partial failures gracefully.
