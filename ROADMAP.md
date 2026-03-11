# Lyric Scroll Roadmap

This document tracks planned features and enhancements for Lyric Scroll.

## Planned Features

### 1. In-App Casting Control

**Status:** Planned

**Problem:** Using the HA cast feature for dashboards is unreliable, particularly with path-related issues.

**Solution:** Add a setting within the Lyric Scroll app to control casting programmatically, eliminating the need for external automations or scripts.

**Requirements:**
- [ ] Add casting settings section in the app settings panel
- [ ] Implement programmatic cast control from within the addon
- [ ] Support selecting target cast devices
- [ ] Handle cast session management (start/stop/reconnect)
- [ ] Investigate and document HA dashboard cast path issues as fallback

---

### 2. Multi-Display Selection

**Status:** In Progress

**Problem:** Need ability to cast lyrics to multiple displays and track which player is currently active.

**Solution:** Generate a `select` entity in Home Assistant that represents the currently selected display where lyrics are being cast.

**Requirements:**
- [x] Add multi-display selection UI in settings
- [x] Add player-to-display mapping in settings
- [x] Persist display preferences (`/data/settings.json`)
- [ ] Create HA `select` entity for active display
- [ ] Sync select state with actual casting target
- [ ] Support switching between displays dynamically

---

### 3. Occupancy-Based Display Automation

**Status:** Planned

**Problem:** Want lyrics to automatically appear on displays in occupied rooms without interrupting existing content.

**Solution:** Create a callable script and automation that updates the display select based on room occupancy.

**Requirements:**
- [ ] Create HA script: `script.lyric_scroll_update_display`
  - Accept target display as parameter
  - Check if content is already playing on target display
  - Only cast if not interrupting existing playback
- [ ] Create HA automation: `automation.lyric_scroll_occupancy`
  - Trigger on occupancy sensor changes
  - Call the update script with appropriate display
  - Handle multiple occupied rooms (priority logic)
- [ ] Document occupancy sensor integration
- [ ] Add "do not disturb" / interruption detection logic

---

### 4. Programmatic Music Assistant Playlist Creation

**Status:** Complete

**Problem:** Need a way for AI systems to create and send playlists to Music Assistant for lyric scrolling.

**Solution:** Create an API/method to programmatically create Music Assistant playlists, with n8n integration.

**Requirements:**
- [x] Research Music Assistant playlist API
- [x] Create endpoint/service for playlist creation
- [x] Native API in Lyric Scroll (no n8n dependency)
  - `POST /api/ma/queue` - Queue tracks on a player
  - `POST /api/ma/play` - Play a single track
  - `POST /api/ma/search` - Search for tracks
  - `GET /api/ma/players` - List available MA players
  - `GET /api/ma/displays` - List available displays
- [x] Settings UI for player/display configuration
- [ ] Document AI integration patterns
- [ ] Support playlist formats (JSON, M3U, etc.)
- [ ] Investigate persistent playlist creation (currently creates queue, not saved playlist)

**Implementation Notes:**
- Native API: `POST http://192.168.6.8:8099/api/ma/queue`
- Settings stored in `/data/settings.json`
- Frontend settings panel for player/display selection
- n8n workflow also available: `n8n-workflows/music-assistant-create-playlist.json`
- Uses HA services: `music_assistant.search` and `music_assistant.play_media`
- Config entry ID discovered automatically
- Enqueue modes: `play` (replace), `add` (append), `next` (play next)

---

### 5. Missing Lyrics Editor with Multi-Source Lookup

**Status:** Planned

**Problem:** When lyrics aren't found automatically, users need a way to manually add them with assistance from various sources.

**Solution:** Create a comprehensive lyrics editor tab with lookup integrations and a timestamping workflow.

**Requirements:**

#### Phase 1: Missing Lyrics Tab
- [ ] Add "Missing Lyrics" tab to the app UI
- [ ] Display list of songs with missing lyrics (already tracked)
- [ ] Show song metadata (artist, title, album art)
- [ ] Allow selecting a song to open lyrics editor modal

#### Phase 2: Lyrics Lookup Sources
- [ ] **Genius Lyrics** button - fetch lyrics from Genius API
- [ ] **AI Lookup** button - prompt AI to research and provide lyrics
  - AI should have ability to search/verify lyrics
  - Paste results into editor
- [ ] **YouTube Captions** option - extract from YouTube video captions/transcript
- [ ] Manual paste fallback for user-sourced lyrics

#### Phase 3: Lyrics Parsing
- [ ] Parse raw/naked lyrics into individual lines
- [ ] AI-assisted line splitting (smart paragraph/verse detection)
- [ ] Manual line editing/splitting interface
- [ ] Preview parsed lines before timestamping

#### Phase 4: Timestamp Editor
- [ ] Audio playback controls (play/pause, seek)
- [ ] "Mark Line Start" button - press at beginning of each line
- [ ] "Mark Line End" button - press at end of each line (optional)
- [ ] Visual timeline showing line markers
- [ ] Adjust/fine-tune timestamps manually
- [ ] Preview synced lyrics with playback

#### Phase 5: Save & Contribute
- [ ] Save to local cache (LRC format)
- [ ] Option to contribute to LRCLIB (community contribution)
- [ ] Export LRC file for manual backup

**Technical Notes:**
- Genius API requires API key (user configurable in settings)
- YouTube captions via youtube-transcript API or yt-dlp
- LRC format: `[mm:ss.xx]Lyric line text`

---

### 6. Dynamic Lyrics Sync (Seek/Skip Tracking)

**Status:** Planned

**Problem:** If the song is rewound, fast-forwarded, or a section is skipped, the lyrics do not resync and continue from their previous position.

**Solution:** Make lyrics actively track the current playback position, jumping to the correct line when position changes significantly.

**Requirements:**
- [ ] Detect significant position changes (>2 seconds delta from expected)
- [ ] Binary search to find correct lyric line for new position
- [ ] Smooth transition to new position (animation)
- [ ] Handle rapid seeking (debounce/throttle)
- [ ] Handle playback rate changes (1.5x, 2x speed)
- [ ] Keep sync through pause/resume cycles

**Technical Notes:**
- Compare expected position (last known + elapsed time) vs reported position
- If delta exceeds threshold, resync to reported position
- May need to request position updates more frequently during active playback

---

### 7. Interactive Timeline with Scrubbing

**Status:** Planned

**Problem:** No visual indication of song progress or ability to navigate within the song.

**Solution:** Add a timeline/progress bar that shows current position and allows scrubbing.

**Requirements:**
- [ ] Visual timeline bar showing song progress
- [ ] Current position indicator
- [ ] Lyric line markers on timeline (optional)
- [ ] Click/drag to scrub to position
- [ ] Send seek command to media player on scrub
- [ ] Settings toggle for timeline visibility:
  - `visible` - Always show timeline
  - `ducking` - Show on hover/interaction, fade out otherwise
  - `off` - Never show timeline

**Design Considerations:**
- Timeline should be minimal/unobtrusive for display mode
- Consider touch-friendly scrubbing for tablet displays
- May show time elapsed / time remaining

---

## Future Ideas

*Ideas for future consideration - not yet planned*

- Spotify Connect integration
- YouTube Music direct integration
- Lyrics caching/offline mode
- Custom theme editor
- Karaoke mode with pitch detection

---

## Changelog

| Date | Update |
|------|--------|
| 2026-03-11 | Initial roadmap created with 4 planned features |
| 2026-03-11 | Feature 4: Created n8n workflow for MA playlist/queue creation via HA services |
| 2026-03-11 | Feature 4: Added native API to Lyric Scroll (`/api/ma/*` endpoints) - no n8n dependency |
| 2026-03-11 | Feature 2: Added player/display selection settings in frontend |
| 2026-03-11 | Added Feature 5: Missing Lyrics Editor with multi-source lookup (Genius, AI, YouTube) |
| 2026-03-11 | Added Feature 6: Dynamic Lyrics Sync for seek/skip tracking |
| 2026-03-11 | Added Feature 7: Interactive Timeline with scrubbing |
