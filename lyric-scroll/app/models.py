"""Data models for Lyric Scroll."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrackInfo:
    """Information about the currently playing track."""
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    content_type: str = ""  # music, video, tvshow, etc.

    def __eq__(self, other):
        if not isinstance(other, TrackInfo):
            return False
        return self.title == other.title and self.artist == other.artist

    def __hash__(self):
        return hash((self.title, self.artist))

    def is_likely_music(self) -> bool:
        """Heuristic check if this is likely music vs video/podcast/stream."""
        # Check content type
        if self.content_type:
            content_lower = self.content_type.lower()
            # Explicit music types
            if content_lower in ("music", "song", "track"):
                return True
            # Explicit non-music types
            if content_lower in ("video", "tvshow", "movie", "episode", "podcast"):
                return False

        # Check duration - music is typically 1-15 minutes
        # Less than 30 seconds or more than 20 minutes is suspicious
        if self.duration_ms > 0:
            duration_min = self.duration_ms / 1000 / 60
            if duration_min > 20:
                return False  # Probably a video/podcast/stream
            if duration_min < 0.5:
                return False  # Too short, probably a sound effect

        # Check title for non-music indicators
        title_lower = self.title.lower()
        non_music_keywords = [
            "live stream", "livestream", "live trial", "episode", "ep.",
            "podcast", "audiobook", "chapter", "part 1", "part 2",
            "interview", "reaction", "review", "tutorial", "how to",
            "news", "update", "vlog", "day in", "full movie"
        ]
        for keyword in non_music_keywords:
            if keyword in title_lower:
                return False

        # If we have an artist, it's more likely music
        if self.artist:
            return True

        # Default: if we can't determine, assume it might be music
        return True


@dataclass
class PlaybackState:
    """Current playback state from media player."""
    state: str  # playing, paused, idle, off
    position_ms: int = 0
    entity_id: str = ""
    track: Optional[TrackInfo] = None


@dataclass
class LyricWord:
    """A single word with timing (for enhanced LRC)."""
    timestamp_ms: int
    text: str


@dataclass
class LyricLine:
    """A single line of lyrics with timing."""
    timestamp_ms: int
    text: str
    words: list[LyricWord] = field(default_factory=list)


@dataclass
class Lyrics:
    """Complete lyrics for a track."""
    lines: list[LyricLine]
    source: str  # lrclib, musixmatch, genius, cache
    synced: bool  # True if has timing data
    track: Optional[TrackInfo] = None
