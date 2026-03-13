"""Lyrics cache management."""

import os
import re
import shutil
import logging
import aiofiles
from typing import Optional

logger = logging.getLogger(__name__)

# Default cache directory (HA addon data volume)
DEFAULT_CACHE_DIR = "/data/cache"

# LRC export directory (HA shared media folder)
LRC_EXPORT_DIR = "/media/my_media/prox_share"


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name)
    name = name.strip('._')
    return name[:100]  # Limit length


class LyricsCache:
    """Simple file-based lyrics cache."""

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, export_enabled: bool = False):
        self.cache_dir = cache_dir
        self.export_enabled = export_enabled
        self.export_dir = LRC_EXPORT_DIR
        os.makedirs(cache_dir, exist_ok=True)
        if export_enabled:
            try:
                os.makedirs(self.export_dir, exist_ok=True)
                logger.info(f"LRC export enabled: {self.export_dir}")
            except Exception as e:
                logger.warning(f"Could not create export dir {self.export_dir}: {e}")

    def _get_path(self, artist: str, title: str) -> str:
        """Get cache file path for a track."""
        safe_artist = sanitize_filename(artist)
        safe_title = sanitize_filename(title)
        filename = f"{safe_artist}_{safe_title}.lrc"
        return os.path.join(self.cache_dir, filename)

    async def get(self, artist: str, title: str) -> Optional[str]:
        """Get cached lyrics if available."""
        path = self._get_path(artist, title)

        if not os.path.exists(path):
            return None

        try:
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                content = await f.read()
                logger.info(f"Cache hit: {artist} - {title}")
                return content
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None

    async def set(self, artist: str, title: str, content: str) -> None:
        """Cache lyrics for a track."""
        path = self._get_path(artist, title)

        try:
            async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                await f.write(content)
                logger.info(f"Cached: {artist} - {title}")

            # Also export to external folder if enabled
            if self.export_enabled:
                await self._export_lrc(artist, title, content)
        except Exception as e:
            logger.error(f"Error writing cache: {e}")

    async def _export_lrc(self, artist: str, title: str, content: str) -> None:
        """Export LRC file to external folder for LRC+ editor."""
        safe_artist = sanitize_filename(artist)
        safe_title = sanitize_filename(title)
        filename = f"{safe_artist} - {safe_title}.lrc"
        export_path = os.path.join(self.export_dir, filename)

        try:
            async with aiofiles.open(export_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            logger.info(f"Exported LRC: {export_path}")
        except Exception as e:
            logger.warning(f"Failed to export LRC to {export_path}: {e}")

    def has(self, artist: str, title: str) -> bool:
        """Check if lyrics are cached."""
        return os.path.exists(self._get_path(artist, title))
