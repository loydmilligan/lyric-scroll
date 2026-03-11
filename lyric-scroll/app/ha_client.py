"""Home Assistant WebSocket API client."""

import os
import json
import asyncio
import logging
from typing import Optional, Callable, Any

import aiohttp

from models import TrackInfo, PlaybackState

logger = logging.getLogger(__name__)

# HA Supervisor API endpoint
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


class HAClient:
    """WebSocket client for Home Assistant API."""

    def __init__(
        self,
        on_state_change: Optional[Callable[[PlaybackState], Any]] = None,
        media_players: Optional[list[str]] = None
    ):
        self.on_state_change = on_state_change
        self.media_players = media_players or []  # Empty = all media_players
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._msg_id = 0
        self._running = False
        self._subscription_id: Optional[int] = None
        self._reconnect_delay = 1

    async def connect(self) -> bool:
        """Connect to Home Assistant WebSocket API."""
        try:
            if not SUPERVISOR_TOKEN:
                logger.error("SUPERVISOR_TOKEN not set")
                return False

            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                SUPERVISOR_WS_URL,
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
            )

            # Wait for auth_required
            msg = await self._ws.receive_json()
            if msg.get("type") != "auth_required":
                logger.error(f"Unexpected message: {msg}")
                return False

            # Authenticate
            await self._ws.send_json({
                "type": "auth",
                "access_token": SUPERVISOR_TOKEN
            })

            msg = await self._ws.receive_json()
            if msg.get("type") != "auth_ok":
                logger.error(f"Auth failed: {msg}")
                return False

            logger.info("Connected to Home Assistant")
            self._reconnect_delay = 1
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Home Assistant."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    def _next_id(self) -> int:
        """Get next message ID."""
        self._msg_id += 1
        return self._msg_id

    async def _send(self, msg: dict) -> int:
        """Send a message and return its ID."""
        msg_id = self._next_id()
        msg["id"] = msg_id
        await self._ws.send_json(msg)
        return msg_id

    async def subscribe_entities(self) -> bool:
        """Subscribe to state changes for media_player entities."""
        try:
            # Subscribe to state_changed events
            msg_id = await self._send({
                "type": "subscribe_events",
                "event_type": "state_changed"
            })

            # Wait for confirmation
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("id") == msg_id:
                        if data.get("success"):
                            self._subscription_id = msg_id
                            logger.info("Subscribed to state changes")
                            return True
                        else:
                            logger.error(f"Subscription failed: {data}")
                            return False

            return False
        except Exception as e:
            logger.error(f"Subscription error: {e}")
            return False

    async def get_states(self) -> list[dict]:
        """Get current states of all entities."""
        try:
            msg_id = await self._send({"type": "get_states"})

            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("id") == msg_id:
                        if data.get("success"):
                            return data.get("result", [])
                        break

            return []
        except Exception as e:
            logger.error(f"Get states error: {e}")
            return []

    def _parse_media_player_state(self, entity_id: str, state: str, attributes: dict) -> PlaybackState:
        """Parse media_player entity state into PlaybackState."""
        track = None

        title = attributes.get("media_title", "")
        artist = attributes.get("media_artist", "")
        duration_sec = attributes.get("media_duration", 0) or 0
        content_type = attributes.get("media_content_type", "")

        if title or artist:
            track = TrackInfo(
                title=title,
                artist=artist,
                album=attributes.get("media_album_name", ""),
                duration_ms=int(duration_sec * 1000),
                content_type=content_type
            )

        position_ms = int(attributes.get("media_position", 0) * 1000)

        return PlaybackState(
            state=state,
            position_ms=position_ms,
            entity_id=entity_id,
            track=track
        )

    def _should_track_entity(self, entity_id: str) -> bool:
        """Check if we should track this entity."""
        if not entity_id.startswith("media_player."):
            return False

        # If no specific players configured, track all
        if not self.media_players:
            return True

        return entity_id in self.media_players

    async def _handle_event(self, event: dict) -> None:
        """Handle a state_changed event."""
        event_data = event.get("data", {})
        entity_id = event_data.get("entity_id", "")

        if not self._should_track_entity(entity_id):
            return

        new_state = event_data.get("new_state", {})
        if not new_state:
            return

        state = new_state.get("state", "")
        attributes = new_state.get("attributes", {})

        playback_state = self._parse_media_player_state(entity_id, state, attributes)

        logger.debug(f"Media player update: {entity_id} -> {state}")

        if self.on_state_change:
            await self.on_state_change(playback_state)

    async def run(self) -> None:
        """Run the client, handling messages and reconnecting as needed."""
        self._running = True

        while self._running:
            try:
                if not await self.connect():
                    logger.warning(f"Connection failed, retrying in {self._reconnect_delay}s")
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 60)
                    continue

                if not await self.subscribe_entities():
                    logger.warning("Subscription failed, reconnecting...")
                    await self.disconnect()
                    continue

                # Get initial states
                states = await self.get_states()
                for state in states:
                    entity_id = state.get("entity_id", "")
                    if self._should_track_entity(entity_id):
                        playback_state = self._parse_media_player_state(
                            entity_id,
                            state.get("state", ""),
                            state.get("attributes", {})
                        )
                        if self.on_state_change and playback_state.track:
                            await self.on_state_change(playback_state)

                # Listen for events
                async for msg in self._ws:
                    if not self._running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "event":
                            event = data.get("event", {})
                            if event.get("event_type") == "state_changed":
                                await self._handle_event(event)

                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning("WebSocket closed/error")
                        break

            except Exception as e:
                logger.error(f"Run error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

        await self.disconnect()
