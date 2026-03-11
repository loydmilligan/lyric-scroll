"""Music Assistant client - calls MA services via Home Assistant API."""

import os
import logging
from typing import Optional, Any

import aiohttp

logger = logging.getLogger(__name__)

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API_URL = "http://supervisor/core/api"

# Music Assistant config entry ID (discovered at runtime)
MA_CONFIG_ENTRY_ID: Optional[str] = None


class MAClient:
    """Client for Music Assistant via Home Assistant services."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.config_entry_id: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _call_service(
        self,
        domain: str,
        service: str,
        data: dict,
        return_response: bool = False
    ) -> dict:
        """Call a Home Assistant service."""
        session = await self._get_session()

        url = f"{HA_API_URL}/services/{domain}/{service}"
        if return_response:
            url += "?return_response"

        try:
            async with session.post(
                url,
                json=data,
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.error(f"Service call failed: {resp.status} - {text}")
                    return {"error": text, "status": resp.status}
        except Exception as e:
            logger.error(f"Service call error: {e}")
            return {"error": str(e)}

    async def _get_api(self, endpoint: str) -> dict:
        """Make a GET request to HA API."""
        session = await self._get_session()

        try:
            async with session.get(
                f"{HA_API_URL}/{endpoint}",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"Status {resp.status}"}
        except Exception as e:
            logger.error(f"API GET error: {e}")
            return {"error": str(e)}

    async def discover_config_entry(self) -> Optional[str]:
        """Discover the Music Assistant config entry ID."""
        if self.config_entry_id:
            return self.config_entry_id

        result = await self._get_api("config/config_entries/entry")

        if isinstance(result, list):
            for entry in result:
                if entry.get("domain") == "music_assistant":
                    self.config_entry_id = entry.get("entry_id")
                    logger.info(f"Discovered MA config entry: {self.config_entry_id}")
                    return self.config_entry_id

        logger.warning("Music Assistant config entry not found")
        return None

    async def get_players(self) -> list[dict]:
        """Get all Music Assistant media players."""
        result = await self._get_api("states")

        players = []
        if isinstance(result, list):
            for state in result:
                entity_id = state.get("entity_id", "")
                # MA players typically have mass_player_type attribute or _2 suffix
                attrs = state.get("attributes", {})
                if (entity_id.startswith("media_player.") and
                    (attrs.get("mass_player_type") or entity_id.endswith("_2"))):
                    players.append({
                        "entity_id": entity_id,
                        "friendly_name": attrs.get("friendly_name", entity_id),
                        "state": state.get("state", "unknown"),
                        "mass_player_type": attrs.get("mass_player_type")
                    })

        return players

    async def get_cast_devices(self) -> list[dict]:
        """Get all Cast devices (displays/speakers)."""
        result = await self._get_api("states")

        devices = []
        if isinstance(result, list):
            for state in result:
                entity_id = state.get("entity_id", "")
                attrs = state.get("attributes", {})
                # Look for cast devices (typically have app_id or device_class speaker)
                if entity_id.startswith("media_player."):
                    device_class = attrs.get("device_class", "")
                    # Exclude MA wrapper entities (those with _2 suffix)
                    if not entity_id.endswith("_2") and device_class in ("speaker", "tv", ""):
                        devices.append({
                            "entity_id": entity_id,
                            "friendly_name": attrs.get("friendly_name", entity_id),
                            "state": state.get("state", "unknown"),
                            "device_class": device_class
                        })

        return devices

    async def search(
        self,
        query: str,
        media_types: list[str] = None,
        limit: int = 5
    ) -> dict:
        """Search for music in Music Assistant."""
        config_entry = await self.discover_config_entry()
        if not config_entry:
            return {"error": "Music Assistant not configured"}

        data = {
            "config_entry_id": config_entry,
            "name": query,
            "media_type": media_types or ["track"],
            "limit": limit
        }

        result = await self._call_service(
            "music_assistant", "search", data, return_response=True
        )

        # Extract service response
        if "service_response" in result:
            return result["service_response"]
        return result

    async def play_media(
        self,
        entity_id: str,
        media_id: str,
        media_type: str = "track",
        enqueue: str = "play"
    ) -> dict:
        """Play media on a Music Assistant player."""
        data = {
            "entity_id": entity_id,
            "media_id": media_id,
            "media_type": media_type,
            "enqueue": enqueue
        }

        return await self._call_service("music_assistant", "play_media", data)

    async def queue_tracks(
        self,
        entity_id: str,
        tracks: list[str],
        enqueue: str = "play"
    ) -> dict:
        """Search and queue multiple tracks on a player.

        Args:
            entity_id: The MA player entity (e.g., media_player.office_2)
            tracks: List of track queries (e.g., ["Daft Punk - One More Time"])
            enqueue: 'play' (replace), 'add' (append), 'next' (play next)

        Returns:
            Summary with added and missing tracks
        """
        added = []
        missing = []

        for i, track_query in enumerate(tracks):
            # Search for the track
            search_result = await self.search(track_query, ["track"], limit=1)

            tracks_found = search_result.get("tracks", [])
            if tracks_found:
                track = tracks_found[0]
                track_uri = track.get("uri")

                if track_uri:
                    # First track uses specified enqueue, rest use 'add'
                    mode = enqueue if i == 0 else "add"
                    await self.play_media(entity_id, track_uri, "track", mode)

                    added.append({
                        "query": track_query,
                        "uri": track_uri,
                        "name": track.get("name"),
                        "artist": track.get("artists", [{}])[0].get("name")
                    })
                else:
                    missing.append({"query": track_query, "reason": "no URI"})
            else:
                missing.append({"query": track_query, "reason": "not found"})

        return {
            "success": True,
            "entity_id": entity_id,
            "added_count": len(added),
            "missing_count": len(missing),
            "added": added,
            "missing": missing
        }
