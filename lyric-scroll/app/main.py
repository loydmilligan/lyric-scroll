#!/usr/bin/env python3
"""Lyric Scroll - Main entry point."""

import asyncio
import json
import logging
import os
import signal
from dataclasses import asdict
from typing import Optional

from aiohttp import web

from models import TrackInfo, PlaybackState, Lyrics
from ha_client import HAClient
from lyrics_fetcher import LyricsFetcher
from cache import LyricsCache

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

        self.current_track: Optional[TrackInfo] = None
        self.current_lyrics: Optional[Lyrics] = None
        self.current_state: str = "idle"
        self.current_position_ms: int = 0
        self.active_entity: Optional[str] = None  # Which media_player we're tracking

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

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp application."""
        app = web.Application()

        # Routes
        app.router.add_get('/', self.index_handler)
        app.router.add_get('/ws', self.websocket_handler)
        app.router.add_static('/css', '/frontend/css')
        app.router.add_static('/js', '/frontend/js')

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
        await runner.cleanup()
        logger.info("Shutdown complete")


async def main() -> None:
    """Main entry point."""
    app = LyricScrollApp()
    await app.run()


if __name__ == '__main__':
    asyncio.run(main())
