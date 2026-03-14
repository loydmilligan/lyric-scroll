# LRC+ Editor Specification

## Overview

A web-based editor for creating and editing LRC+ enhanced lyrics files. LRC+ extends the standard LRC format with end timestamps, voice/singer identification, section markers, and instrumental labels.

## LRC+ Format

### Standard LRC
```
[00:12.34]Lyric line text
```

### LRC+ Enhanced
```
[00:12.34>00:17.89]Lyric line text
```

### Attribute Tags
- `v:` - Voice/singer identification for color-coding different vocalists
- `s:` - Section markers (verse, chorus, bridge)
- `bg` - Background vocals
- `inst` - Instrumental sections

### Header Metadata
- BPM, musical key, time signature
- Voice definitions with color assignments

### Section Markers
- `[#verse1]`, `[#chorus]` for navigation

## Features

### Phase 1: LRC+ Parser & Renderer
- Extend lyrics parser to support LRC+ syntax
- Parse end timestamps `[start>end]`
- Parse attribute tags (voice, section, background, instrumental)
- Extract header metadata
- Implement karaoke-style highlighting using end timestamps
- Color-code lyrics by voice/singer
- Display section labels
- Show instrumental section screens
- Graceful fallback for standard LRC files

### Phase 2: LRC+ Web Editor
- Create web-based LRC+ editor interface
- Audio file upload/loading
- Load existing LRC file as base
- Audio playback controls
- "Mark Start" and "Mark End" timestamp buttons
- UI for tagging sections (verse, chorus, bridge)
- UI for assigning voices/singers to lines
- Voice color picker/manager
- Mark instrumental sections
- Real-time preview of formatted lyrics
- Export to LRC+ format
- Save/load work-in-progress

### Phase 3: LRC+ Auto-Converter (Lower Priority)
- Analyze audio to detect sections
- Detect instrumental breaks
- Estimate line end timestamps
- Auto-suggest section boundaries
- Machine learning for voice separation detection
- Export suggested LRC+ for manual review

## Technical Stack

- **Frontend**: React/Svelte with TypeScript
- **Audio**: Web Audio API for playback and waveform visualization
- **Storage**: Local storage + optional cloud sync
- **Export**: LRC+ format (.lrcx extension)

## User Interface

### Main Editor View
```
┌─────────────────────────────────────────────────────────┐
│  [Open Audio] [Load LRC] [Save] [Export]                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ▶ 00:00 ────────○───────────────────────── 03:45      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Lyrics Editor                    │  Preview            │
│  ─────────────────                │  ─────────          │
│  [#verse1]                        │  ♪ First line       │
│  [00:12.34>00:17.89] First line   │    of the song     │
│  [00:17.90>00:22.45] Second line  │                    │
│  [#chorus]                        │                    │
│  [00:22.50>00:28.00] Chorus line  │                    │
│                                   │                    │
├─────────────────────────────────────────────────────────┤
│  [Mark Start] [Mark End] [Add Section] [Set Voice]      │
└─────────────────────────────────────────────────────────┘
```

### Voice Manager
- Define voices/singers with names and colors
- Assign lines to voices
- Visual color coding in editor and preview

### Section Manager
- Define sections (verse, chorus, bridge, instrumental)
- Navigate between sections
- Collapse/expand sections in editor

## Integration with Lyric Scroll

- Import LRC+ files into Lyric Scroll cache
- Real-time preview on connected displays
- Sync with Music Assistant playback

## File Format

### LRC+ File Structure
```
[ar:Artist Name]
[ti:Song Title]
[al:Album Name]
[bpm:120]
[key:Cm]
[voice:main:Matt:#FF0000]
[voice:bg:Harmony:#00FF00]

[#intro]
[00:00.00>00:05.00|inst]

[#verse1]
[00:05.00>00:10.00|v:main]First verse line
[00:10.00>00:15.00|v:main]Second verse line

[#chorus]
[00:15.00>00:20.00|v:main|s:chorus]Chorus line one
[00:20.00>00:25.00|v:bg]Background harmony
```

## Deployment

- Standalone web app (can be deployed to Vercel/Netlify)
- Optional integration as Lyric Scroll addon
- PWA support for offline editing
