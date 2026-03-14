# Song-Links API Integration

This document describes the song-links Edge Function used in the Talking Music League project, which can be referenced or adapted for cross-platform music link resolution.

## Overview

The function uses the **[Odesli/Song.link API](https://odesli.co/)** to convert music links from one streaming platform to equivalent links across all major services.

**API Endpoint:**
```
https://api.song.link/v1-alpha.1/links
```

This is a **free API** (no API key required for basic usage) that accepts a music link and returns links for all available platforms.

## Supported Platforms

| Platform | API Key | Description |
|----------|---------|-------------|
| Spotify | `spotify` | Spotify streaming links |
| Apple Music | `appleMusic` | Apple Music links |
| YouTube | `youtube` | YouTube video links |
| YouTube Music | `youtubeMusic` | YouTube Music links |
| Tidal | `tidal` | Tidal streaming links |
| Deezer | `deezer` | Deezer streaming links |
| Amazon Music | `amazonMusic` | Amazon Music links |
| Pandora | `pandora` | Pandora links |
| Napster | `napster` | Napster links |
| Soundcloud | `soundcloud` | Soundcloud links |
| Song.link Page | `pageUrl` | Universal song.link landing page |

### Not Supported

- **Sonos** - Not a streaming service; Sonos is a hardware platform that plays FROM other services
- **Chromecast** - Hardware casting protocol, not a music service
- **Local files** - Only works with streaming service URLs

## API Request

### Basic Request

```bash
curl "https://api.song.link/v1-alpha.1/links?url=https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
```

### Request Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | URL or URI from any supported platform |
| `userCountry` | No | ISO 3166-1 alpha-2 country code (e.g., `US`) |
| `songIfSingle` | No | If true, returns song link even if input is a single-track album |

## API Response

```json
{
  "entityUniqueId": "SPOTIFY_SONG::4iV5W9uYEdYUVa79Axb7Rh",
  "userCountry": "US",
  "pageUrl": "https://song.link/us/i/1440818345",
  "entitiesByUniqueId": {
    "SPOTIFY_SONG::4iV5W9uYEdYUVa79Axb7Rh": {
      "id": "4iV5W9uYEdYUVa79Axb7Rh",
      "type": "song",
      "title": "Hotline Bling",
      "artistName": "Drake",
      "thumbnailUrl": "https://...",
      "apiProvider": "spotify",
      "platforms": ["spotify"]
    }
  },
  "linksByPlatform": {
    "spotify": {
      "country": "US",
      "url": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh",
      "entityUniqueId": "SPOTIFY_SONG::4iV5W9uYEdYUVa79Axb7Rh"
    },
    "appleMusic": {
      "country": "US",
      "url": "https://music.apple.com/us/album/...",
      "entityUniqueId": "ITUNES_SONG::1440818345"
    },
    "youtube": {
      "country": "US",
      "url": "https://www.youtube.com/watch?v=...",
      "entityUniqueId": "YOUTUBE_VIDEO::..."
    }
  }
}
```

## TypeScript Implementation

### Types

```typescript
interface SongLinkResponse {
  entityUniqueId: string;
  userCountry: string;
  pageUrl: string;
  entitiesByUniqueId: Record<string, {
    id: string;
    type: string;
    title?: string;
    artistName?: string;
    thumbnailUrl?: string;
    apiProvider: string;
    platforms: string[];
  }>;
  linksByPlatform: Record<string, {
    country: string;
    url: string;
    entityUniqueId: string;
  }>;
}

interface PlatformLinks {
  spotify?: string;
  appleMusic?: string;
  youtube?: string;
  youtubeMusic?: string;
  tidal?: string;
  deezer?: string;
  amazonMusic?: string;
  pandora?: string;
  songLink?: string;
}
```

### Fetch Function

```typescript
const SONG_LINK_API = "https://api.song.link/v1-alpha.1/links";

async function fetchSongLinks(spotifyUri: string): Promise<PlatformLinks> {
  // Convert URI to URL if needed
  let url = spotifyUri;
  if (spotifyUri.startsWith("spotify:track:")) {
    const trackId = spotifyUri.replace("spotify:track:", "");
    url = `https://open.spotify.com/track/${trackId}`;
  }

  const response = await fetch(
    `${SONG_LINK_API}?url=${encodeURIComponent(url)}`
  );

  if (!response.ok) {
    throw new Error(`song.link API error: ${response.status}`);
  }

  const data: SongLinkResponse = await response.json();

  // Build platform links
  const links: PlatformLinks = {
    songLink: data.pageUrl,
  };

  const platforms = [
    'spotify', 'appleMusic', 'youtube', 'youtubeMusic',
    'tidal', 'deezer', 'amazonMusic', 'pandora'
  ] as const;

  for (const platform of platforms) {
    if (data.linksByPlatform[platform]) {
      links[platform] = data.linksByPlatform[platform].url;
    }
  }

  return links;
}
```

## Rate Limiting

The song.link API has rate limits (exact limits not publicly documented). Best practices:

- Add **100-150ms delay** between consecutive requests
- Batch requests should be limited to **~10 per batch**
- Cache results when possible (links rarely change)
- Use the universal `pageUrl` as a fallback if specific platform fails

## Use Cases

1. **Single Track Conversion**: Convert a Spotify link to Apple Music for sharing
2. **Batch Processing**: Populate alternative platform links for a playlist
3. **Universal Links**: Generate a song.link page that auto-redirects users to their preferred platform
4. **Metadata Extraction**: Get song title, artist, and thumbnail from any platform URL

## References

- [Odesli/Song.link Official Site](https://odesli.co/)
- [Song.link API Documentation](https://www.notion.so/API-d0ebe08a5e304a55928405eb682f6741)
- [GitHub: odesli.js wrapper](https://github.com/MattrAus/odesli.js/)
- [GitHub: python-odesli wrapper](https://github.com/fabian-thomas/python-odesli)
