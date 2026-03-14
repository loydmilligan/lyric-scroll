#!/usr/bin/env python3
"""
Home Assistant Control Scripts for Lyric Scroll Testing

Provides utilities to:
- Restart the Lyric Scroll addon
- Control media playback (play/pause/stop)
- Query player state
- Trigger test scenarios

Usage:
    python3 ha_control.py restart-addon
    python3 ha_control.py play
    python3 ha_control.py pause
    python3 ha_control.py status
    python3 ha_control.py position
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


# Configuration
HA_URL = "http://192.168.6.8:8123"
HA_TOKEN = os.environ.get("HA_TOKEN", "")
ADDON_SLUG = "local_lyric_scroll"  # Addon slug in HA
PLAYER_ENTITY = "media_player.office"
ADDON_URL = "https://lyric-scroll.mattmariani.com"


def check_token():
    """Verify HA_TOKEN is set."""
    if not HA_TOKEN:
        print("ERROR: HA_TOKEN environment variable not set")
        print("Set it with: export HA_TOKEN='your-long-lived-token'")
        sys.exit(1)


def ha_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a request to Home Assistant API."""
    check_token()

    url = f"{HA_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data or {}, timeout=30)
        else:
            raise ValueError(f"Unknown method: {method}")

        resp.raise_for_status()

        # Some endpoints return empty responses
        if resp.text:
            return resp.json()
        return {"status": "ok"}

    except requests.exceptions.RequestException as e:
        print(f"ERROR: HA request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)


def addon_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a request to Lyric Scroll addon API."""
    url = f"{ADDON_URL}{endpoint}"

    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=data or {}, timeout=10)
        else:
            raise ValueError(f"Unknown method: {method}")

        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Addon request failed: {e}")
        sys.exit(1)


# === Commands ===

def cmd_restart_addon():
    """Restart the Lyric Scroll addon."""
    print(f"Restarting addon: {ADDON_SLUG}...")

    # The Supervisor API is internal-only, so we use a workaround:
    # Call the hassio.addon_restart service
    result = ha_request("POST", "/api/services/hassio/addon_restart", {
        "addon": ADDON_SLUG
    })

    print("Restart command sent. Waiting for addon to come back up...")

    # Wait and check if addon is responding
    for i in range(30):
        time.sleep(2)
        try:
            resp = requests.get(f"{ADDON_URL}/api/settings", timeout=5)
            if resp.status_code == 200:
                print(f"Addon is back up after ~{(i+1)*2} seconds")
                return
        except:
            pass
        print(f"  Waiting... ({(i+1)*2}s)")

    print("WARNING: Addon did not respond within 60 seconds")


def cmd_play():
    """Start/resume playback."""
    print(f"Starting playback on {PLAYER_ENTITY}...")
    result = ha_request("POST", "/api/services/media_player/media_play", {
        "entity_id": PLAYER_ENTITY
    })
    print("Play command sent")


def cmd_pause():
    """Pause playback."""
    print(f"Pausing playback on {PLAYER_ENTITY}...")
    result = ha_request("POST", "/api/services/media_player/media_pause", {
        "entity_id": PLAYER_ENTITY
    })
    print("Pause command sent")


def cmd_stop():
    """Stop playback."""
    print(f"Stopping playback on {PLAYER_ENTITY}...")
    result = ha_request("POST", "/api/services/media_player/media_stop", {
        "entity_id": PLAYER_ENTITY
    })
    print("Stop command sent")


def cmd_status():
    """Get current player status."""
    print(f"Getting status for {PLAYER_ENTITY}...")

    # Get from HA
    state = ha_request("GET", f"/api/states/{PLAYER_ENTITY}")

    print(f"\n=== Home Assistant State ===")
    print(f"State: {state.get('state')}")

    attrs = state.get("attributes", {})
    print(f"Track: {attrs.get('media_artist', 'Unknown')} - {attrs.get('media_title', 'Unknown')}")
    print(f"Album: {attrs.get('media_album_name', 'Unknown')}")
    print(f"Position: {attrs.get('media_position', 0):.1f}s / {attrs.get('media_duration', 0):.1f}s")
    print(f"Volume: {attrs.get('volume_level', 0) * 100:.0f}%")

    # Get from addon
    try:
        addon_state = addon_request("GET", "/api/position")
        print(f"\n=== Addon State ===")
        print(f"State: {addon_state.get('state')}")
        print(f"Track: {addon_state.get('track')}")
        print(f"Position: {addon_state.get('position_ms', 0)}ms ({addon_state.get('position_ms', 0)/1000:.1f}s)")
    except:
        print("\n=== Addon State ===")
        print("Could not reach addon")


def cmd_position():
    """Get current position from both HA and addon (for sync comparison)."""
    timestamp = datetime.now().isoformat()
    print(f"Timestamp: {timestamp}")
    print()

    # Query both in quick succession
    t1 = time.time()
    addon_data = addon_request("GET", "/api/position")
    t2 = time.time()
    ha_state = ha_request("GET", f"/api/states/{PLAYER_ENTITY}")
    t3 = time.time()

    addon_pos_ms = addon_data.get("position_ms", 0)
    ha_pos_sec = ha_state.get("attributes", {}).get("media_position", 0) or 0
    ha_pos_ms = int(ha_pos_sec * 1000)

    print(f"Addon position:  {addon_pos_ms}ms ({addon_pos_ms/1000:.2f}s)  [query took {(t2-t1)*1000:.0f}ms]")
    print(f"HA position:     {ha_pos_ms}ms ({ha_pos_sec:.2f}s)  [query took {(t3-t2)*1000:.0f}ms]")
    print(f"Difference:      {abs(addon_pos_ms - ha_pos_ms)}ms")
    print()
    print(f"Track (addon):   {addon_data.get('track')}")
    print(f"Track (HA):      {ha_state.get('attributes', {}).get('media_title')}")
    print(f"State (addon):   {addon_data.get('state')}")
    print(f"State (HA):      {ha_state.get('state')}")


def cmd_seek(position_sec: float):
    """Seek to a specific position."""
    print(f"Seeking to {position_sec}s on {PLAYER_ENTITY}...")
    result = ha_request("POST", "/api/services/media_player/media_seek", {
        "entity_id": PLAYER_ENTITY,
        "seek_position": position_sec
    })
    print(f"Seek command sent to {position_sec}s")


def cmd_volume(level: float):
    """Set volume level (0.0 - 1.0)."""
    print(f"Setting volume to {level*100:.0f}% on {PLAYER_ENTITY}...")
    result = ha_request("POST", "/api/services/media_player/volume_set", {
        "entity_id": PLAYER_ENTITY,
        "volume_level": level
    })
    print("Volume command sent")


def cmd_addon_settings():
    """Get current addon settings."""
    settings = addon_request("GET", "/api/settings")
    print(json.dumps(settings, indent=2))


def cmd_addon_players():
    """List available MA players."""
    players = addon_request("GET", "/api/ma/players")
    print("=== Music Assistant Players ===")
    for p in players:
        print(f"  {p.get('entity_id')}: {p.get('friendly_name')} [{p.get('state')}]")


def main():
    parser = argparse.ArgumentParser(description="Home Assistant Control for Lyric Scroll Testing")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Addon commands
    subparsers.add_parser("restart-addon", help="Restart the Lyric Scroll addon")
    subparsers.add_parser("addon-settings", help="Get addon settings")
    subparsers.add_parser("addon-players", help="List MA players")

    # Playback commands
    subparsers.add_parser("play", help="Start/resume playback")
    subparsers.add_parser("pause", help="Pause playback")
    subparsers.add_parser("stop", help="Stop playback")

    seek_parser = subparsers.add_parser("seek", help="Seek to position")
    seek_parser.add_argument("position", type=float, help="Position in seconds")

    vol_parser = subparsers.add_parser("volume", help="Set volume")
    vol_parser.add_argument("level", type=float, help="Volume level 0.0-1.0")

    # Status commands
    subparsers.add_parser("status", help="Get full player status")
    subparsers.add_parser("position", help="Get current position (sync comparison)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "restart-addon": cmd_restart_addon,
        "addon-settings": cmd_addon_settings,
        "addon-players": cmd_addon_players,
        "play": cmd_play,
        "pause": cmd_pause,
        "stop": cmd_stop,
        "seek": lambda: cmd_seek(args.position),
        "volume": lambda: cmd_volume(args.level),
        "status": cmd_status,
        "position": cmd_position,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func()
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
