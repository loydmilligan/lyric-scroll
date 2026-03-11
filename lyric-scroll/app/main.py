#!/usr/bin/env python3
"""Lyric Scroll - Main entry point."""

import asyncio
import json
import logging
import os
import signal
from dataclasses import asdict
from typing import Optional

import aiohttp
from aiohttp import web

from models import TrackInfo, PlaybackState, Lyrics
from ha_client import HAClient
from lyrics_fetcher import LyricsFetcher
from cache import LyricsCache
from missing_lyrics import MissingLyricsTracker
from ma_client import MAClient

# Supervisor API for image proxy
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LyricScrollApp:
    """Main application coordinating all components."""

    def __init__(self):
        self.clients: set[web.WebSocketResponse] = set()
        self.cache = LyricsCache()
        self.fetcher = LyricsFetcher(self.cache)
        self.ha_client: Optional[HAClient] = None
        self.ma_client = MAClient()
        self.missing_lyrics = MissingLyricsTracker()

        self.current_track: Optional[TrackInfo] = None
        self.current_lyrics: Optional[Lyrics] = None
        self.current_state: str = "idle"
        self.current_position_ms: int = 0
        self.active_entity: Optional[str] = None  # Which media_player we're tracking

        # Settings stored in /data/settings.json
        self.settings_path = "/data/settings.json"
        self.settings = self._load_settings()

    async def on_state_change(self, state: PlaybackState) -> None:
        """Handle media player state changes from HA."""
        # Only process if this entity is playing, or if it's our active entity
        is_playing = state.state == "playing"
        is_active_entity = state.entity_id == self.active_entity

        # If something else starts playing, switch to it
        if is_playing and state.track:
            # Filter out non-music content
            if not state.track.is_likely_music():
                logger.debug(
                    f"Skipping non-music: {state.track.artist} - {state.track.title} "
                    f"(type={state.track.content_type}, duration={state.track.duration_ms/1000:.0f}s)"
                )
                return

            # New track or different entity started playing
            if state.track != self.current_track or not is_active_entity:
                logger.info(f"Now playing on {state.entity_id}: {state.track.artist} - {state.track.title}")
                self.active_entity = state.entity_id
                self.current_track = state.track
                self.current_state = state.state
                self.current_position_ms = state.position_ms
                await self._fetch_and_broadcast_lyrics(state.track)
                # Autocast to mapped display
                await self._autocast_to_display(state.entity_id)
            else:
                # Same track, just update position
                self.current_position_ms = state.position_ms
                self.current_state = state.state

            # Broadcast position update
            if self.current_lyrics and self.clients:
                logger.info(f"Position: {state.position_ms/1000:.1f}s -> {len(self.clients)} client(s)")
                await self.broadcast({
                    "type": "position",
                    "data": {
                        "position_ms": state.position_ms,
                        "state": state.state
                    }
                })

        # If our active entity stopped playing
        elif is_active_entity and state.state in ("idle", "off", "unavailable", "paused"):
            if state.state == "paused":
                # Just paused, keep lyrics but update state
                self.current_state = state.state
                logger.debug(f"Playback paused on {state.entity_id}")
            else:
                # Stopped completely
                if self.current_track is not None:
                    logger.info(f"Playback stopped on {state.entity_id}")
                    self.current_track = None
                    self.current_lyrics = None
                    self.active_entity = None
                    self.current_state = "idle"
                    await self.broadcast({"type": "idle"})

    async def _fetch_and_broadcast_lyrics(self, track: TrackInfo) -> None:
        """Fetch lyrics for a track and broadcast to clients."""
        # Notify clients we're loading
        await self.broadcast({
            "type": "loading",
            "data": {
                "track": {
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "year": track.year,
                    "album_art_url": track.album_art_url
                }
            }
        })

        # Fetch lyrics
        lyrics = await self.fetcher.fetch(track)

        if lyrics:
            self.current_lyrics = lyrics
            logger.info(f"Got lyrics: {len(lyrics.lines)} lines from {lyrics.source}")

            await self.broadcast({
                "type": "lyrics",
                "data": {
                    "track": {
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "year": track.year,
                        "album_art_url": track.album_art_url
                    },
                    "lyrics": [
                        {"timestamp_ms": line.timestamp_ms, "text": line.text}
                        for line in lyrics.lines
                    ],
                    "synced": lyrics.synced,
                    "source": lyrics.source,
                    "duration_ms": track.duration_ms
                }
            })
        else:
            self.current_lyrics = None

            # Track this song as missing lyrics
            self.missing_lyrics.add(
                artist=track.artist,
                title=track.title,
                album=track.album,
                album_art_url=track.album_art_url,
                entity_id=self.active_entity or ""
            )

            await self.broadcast({
                "type": "no_lyrics",
                "data": {
                    "track": {
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "year": track.year,
                        "album_art_url": track.album_art_url
                    }
                }
            })

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected WebSocket clients."""
        if not self.clients:
            return

        data = json.dumps(message)
        for client in list(self.clients):
            try:
                await client.send_str(data)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                self.clients.discard(client)

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections from frontend."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)
        logger.info(f"WebSocket client connected from {request.remote}. Total clients: {len(self.clients)}")

        try:
            # Send current state to new client
            if self.current_lyrics and self.current_track:
                await ws.send_json({
                    "type": "lyrics",
                    "data": {
                        "track": {
                            "title": self.current_track.title,
                            "artist": self.current_track.artist,
                            "album": self.current_track.album,
                            "year": self.current_track.year,
                            "album_art_url": self.current_track.album_art_url
                        },
                        "lyrics": [
                            {"timestamp_ms": line.timestamp_ms, "text": line.text}
                            for line in self.current_lyrics.lines
                        ],
                        "synced": self.current_lyrics.synced,
                        "source": self.current_lyrics.source,
                        "duration_ms": self.current_track.duration_ms
                    }
                })
                # Also send current position
                await ws.send_json({
                    "type": "position",
                    "data": {
                        "position_ms": self.current_position_ms,
                        "state": self.current_state
                    }
                })
            else:
                await ws.send_json({"type": "idle"})

            # Handle incoming messages
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        logger.info(f"Received from client: {data}")
                        # Handle client messages (settings, resync requests)
                        if data.get("type") == "resync":
                            # Re-send current position
                            await ws.send_json({
                                "type": "position",
                                "data": {
                                    "position_ms": self.current_position_ms,
                                    "state": self.current_state
                                }
                            })
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            self.clients.discard(ws)
            logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

        return ws

    async def index_handler(self, request: web.Request) -> web.FileResponse:
        """Serve the main HTML page."""
        return web.FileResponse('/frontend/index.html')

    async def api_missing_lyrics(self, request: web.Request) -> web.Response:
        """Get list of tracks with missing lyrics."""
        return web.json_response({
            "count": self.missing_lyrics.get_count(),
            "tracks": self.missing_lyrics.get_all()
        })

    async def api_missing_lyrics_delete(self, request: web.Request) -> web.Response:
        """Remove a track from missing lyrics list."""
        try:
            data = await request.json()
            artist = data.get("artist", "")
            title = data.get("title", "")

            if not artist or not title:
                return web.json_response(
                    {"error": "artist and title required"},
                    status=400
                )

            removed = self.missing_lyrics.remove(artist, title)
            return web.json_response({"success": removed})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_missing_lyrics_clear(self, request: web.Request) -> web.Response:
        """Clear all missing lyrics entries."""
        self.missing_lyrics.clear()
        return web.json_response({"success": True})

    async def api_image_proxy(self, request: web.Request) -> web.Response:
        """Proxy images from Home Assistant API."""
        path = request.query.get("path", "")
        if not path or not path.startswith("/api/"):
            return web.Response(status=400, text="Invalid path")

        try:
            ha_url = f"http://supervisor/core{path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    ha_url,
                    headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
                ) as resp:
                    if resp.status != 200:
                        return web.Response(status=resp.status)

                    content_type = resp.headers.get("Content-Type", "image/jpeg")
                    body = await resp.read()
                    return web.Response(
                        body=body,
                        content_type=content_type,
                        headers={"Cache-Control": "max-age=300"}
                    )
        except Exception as e:
            logger.error(f"Image proxy error: {e}")
            return web.Response(status=500, text=str(e))

    def _load_settings(self) -> dict:
        """Load settings from file."""
        default_settings = {
            "ma_players": [],           # List of MA player entity_ids
            "display_mappings": {},     # player_id -> display_id mapping
            "default_player": None,     # Default MA player for queue operations
            "default_display": None,    # Default display for casting
            "autocast_enabled": False,
            "autocast_url": "http://192.168.6.8:8099"
        }

        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path) as f:
                    saved = json.load(f)
                    # Merge with defaults
                    return {**default_settings, **saved}
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

        return default_settings

    def _save_settings(self) -> bool:
        """Save settings to file."""
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False

    async def _autocast_to_display(self, player_entity_id: str) -> None:
        """Cast Lyric Scroll to mapped display if idle."""
        # Check if autocast is enabled
        if not self.settings.get("autocast_enabled", False):
            return

        # Get mapped display for this player
        display_id = self.settings.get("display_mappings", {}).get(player_entity_id)
        if not display_id:
            logger.debug(f"No display mapped for {player_entity_id}")
            return

        # Check if display is idle/off
        display_state = await self.ha_client.get_entity_state(display_id)
        if not display_state:
            logger.warning(f"Could not get state for display {display_id}")
            return

        current_state = display_state.get("state", "")
        if current_state not in ("idle", "off", "unavailable"):
            logger.info(f"Display {display_id} is busy ({current_state}), skipping autocast")
            return

        # Cast the URL to the display
        cast_url = self.settings.get("autocast_url", "http://192.168.6.8:8099")
        success = await self.ha_client.call_service(
            "media_player",
            "play_media",
            {
                "entity_id": display_id,
                "media_content_id": cast_url,
                "media_content_type": "url"
            }
        )
        if success:
            logger.info(f"Auto-cast to {display_id}: {cast_url}")
        else:
            logger.warning(f"Auto-cast failed for {display_id}")

    # ========== Settings API ==========

    async def api_get_settings(self, request: web.Request) -> web.Response:
        """Get current settings."""
        return web.json_response(self.settings)

    async def api_update_settings(self, request: web.Request) -> web.Response:
        """Update settings."""
        try:
            data = await request.json()

            # Update settings (only known keys)
            for key in ["ma_players", "display_mappings", "default_player", "default_display", "autocast_enabled", "autocast_url"]:
                if key in data:
                    self.settings[key] = data[key]

            if self._save_settings():
                return web.json_response({"success": True, "settings": self.settings})
            else:
                return web.json_response({"error": "Failed to save settings"}, status=500)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    # ========== Music Assistant API ==========

    async def api_ma_players(self, request: web.Request) -> web.Response:
        """Get available Music Assistant players."""
        players = await self.ma_client.get_players()
        return web.json_response({"players": players})

    async def api_ma_displays(self, request: web.Request) -> web.Response:
        """Get available Cast displays/speakers."""
        devices = await self.ma_client.get_cast_devices()
        return web.json_response({"displays": devices})

    async def api_ma_search(self, request: web.Request) -> web.Response:
        """Search Music Assistant for tracks."""
        try:
            data = await request.json()
            query = data.get("query", "")
            media_types = data.get("media_types", ["track"])
            limit = data.get("limit", 5)

            if not query:
                return web.json_response({"error": "query required"}, status=400)

            result = await self.ma_client.search(query, media_types, limit)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_ma_play(self, request: web.Request) -> web.Response:
        """Play a track on a Music Assistant player."""
        try:
            data = await request.json()
            entity_id = data.get("entity_id") or self.settings.get("default_player")
            media_id = data.get("media_id")
            media_type = data.get("media_type", "track")
            enqueue = data.get("enqueue", "play")

            if not entity_id:
                return web.json_response({"error": "entity_id required"}, status=400)
            if not media_id:
                return web.json_response({"error": "media_id required"}, status=400)

            result = await self.ma_client.play_media(entity_id, media_id, media_type, enqueue)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_ma_queue(self, request: web.Request) -> web.Response:
        """Queue multiple tracks on a Music Assistant player.

        This is the main endpoint for AI/automation playlist creation.

        Body:
            {
                "entity_id": "media_player.office_2",  // optional if default set
                "tracks": ["Artist - Song", "Artist - Song"],
                "enqueue": "play"  // 'play', 'add', or 'next'
            }
        """
        try:
            data = await request.json()
            entity_id = data.get("entity_id") or self.settings.get("default_player")
            tracks = data.get("tracks") or data.get("songs") or []
            enqueue = data.get("enqueue", "play")

            if not entity_id:
                return web.json_response(
                    {"error": "entity_id required (or set default_player in settings)"},
                    status=400
                )

            if not tracks:
                return web.json_response({"error": "tracks array required"}, status=400)

            # Handle newline-separated string
            if isinstance(tracks, str):
                tracks = [t.strip() for t in tracks.split("\n") if t.strip()]

            result = await self.ma_client.queue_tracks(entity_id, tracks, enqueue)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Queue error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp application."""
        app = web.Application()

        # Routes
        app.router.add_get('/', self.index_handler)
        app.router.add_get('/ws', self.websocket_handler)
        app.router.add_static('/css', '/frontend/css')
        app.router.add_static('/js', '/frontend/js')

        # API routes
        app.router.add_get('/api/missing-lyrics', self.api_missing_lyrics)
        app.router.add_delete('/api/missing-lyrics', self.api_missing_lyrics_delete)
        app.router.add_post('/api/missing-lyrics/clear', self.api_missing_lyrics_clear)
        app.router.add_get('/api/image-proxy', self.api_image_proxy)

        # Settings API
        app.router.add_get('/api/settings', self.api_get_settings)
        app.router.add_post('/api/settings', self.api_update_settings)

        # Music Assistant API
        app.router.add_get('/api/ma/players', self.api_ma_players)
        app.router.add_get('/api/ma/displays', self.api_ma_displays)
        app.router.add_post('/api/ma/search', self.api_ma_search)
        app.router.add_post('/api/ma/play', self.api_ma_play)
        app.router.add_post('/api/ma/queue', self.api_ma_queue)

        return app

    async def run(self) -> None:
        """Run the application."""
        logger.info("Lyric Scroll starting...")

        # Load config
        media_players = []
        options_path = "/data/options.json"
        if os.path.exists(options_path):
            try:
                with open(options_path) as f:
                    options = json.load(f)
                    media_players = options.get("media_players", [])
                    logger.info(f"Configured media players: {media_players}")
            except Exception as e:
                logger.error(f"Error loading options: {e}")

        # Initialize HA client
        self.ha_client = HAClient(
            on_state_change=self.on_state_change,
            media_players=media_players
        )

        # Get ingress port
        port = int(os.environ.get('INGRESS_PORT', 8099))

        # Start web server
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"Web server started on port {port}")

        # Set up shutdown handler
        stop_event = asyncio.Event()

        def handle_signal():
            logger.info("Shutdown signal received")
            stop_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        # Run HA client in background
        ha_task = asyncio.create_task(self.ha_client.run())

        # Wait for shutdown
        await stop_event.wait()

        # Cleanup
        logger.info("Shutting down...")
        self.ha_client._running = False

        # Give HA client time to disconnect gracefully
        await self.ha_client.disconnect()

        ha_task.cancel()
        try:
            await ha_task
        except asyncio.CancelledError:
            pass

        await self.fetcher.close()
        await self.ma_client.close()
        await runner.cleanup()
        logger.info("Shutdown complete")


async def main() -> None:
    """Main entry point."""
    app = LyricScrollApp()
    await app.run()


if __name__ == '__main__':
    asyncio.run(main())
