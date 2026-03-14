#!/usr/bin/env python3
"""
Lyric Scroll Sync Verification Test

This script verifies that lyrics are properly synchronized with audio playback.
It captures multiple snapshots of both audio position and displayed lyrics,
then compares them to detect sync issues like drift, jumps, or stuttering.

Usage:
    python3 sync_test.py [--checks N] [--interval SECONDS] [--play] [--track TRACK_ID]

Arguments:
    --checks N         Number of sync checks (default: 5)
    --interval SECONDS Seconds between checks (default: 10)
    --play             Start playback before testing
    --track TRACK_ID   Spotify track ID to play (default: Queen - Another One Bites The Dust)

Examples:
    python3 sync_test.py --play
    python3 sync_test.py --play --track "spotify--RWrw92M3://track/XXXXXXXXXXXXXXX"
    python3 sync_test.py --checks 10 --interval 5

Output:
    - Screenshots saved to tests/screenshots/
    - Test log saved to tests/sync_test_TIMESTAMP.log
    - Summary printed to console
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "lyric-scroll" / "app"))

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Page = None  # Type annotation fallback
    print("WARNING: playwright not installed. Screenshots will be skipped.")
    print("Install with: pip install playwright && playwright install chromium")


# Configuration
ADDON_URL = "https://lyric-scroll.mattmariani.com"
HA_URL = "http://192.168.6.8:8123"
HA_TOKEN = os.environ.get("HA_TOKEN", "")
PLAYER_ENTITY = "media_player.office_2"  # Primary test player
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
LOG_DIR = Path(__file__).parent / "logs"
LRC_DIR = Path("/mnt/c/Users/mmariani/Music/lrc")
DEFAULT_TRACK = "spotify--RWrw92M3://track/57JVGBtBLCfHw2muk5416J"  # Queen - Another One Bites The Dust


@dataclass
class SyncSnapshot:
    """A single point-in-time capture of sync state."""
    timestamp: str  # ISO timestamp when snapshot was taken
    timestamp_ms: int  # Unix timestamp in milliseconds

    # Audio state (from addon API)
    addon_position_ms: int
    addon_state: str
    addon_track: Optional[str]

    # Audio state (from HA API for comparison)
    ha_position_sec: float
    ha_state: str
    ha_track: Optional[str]

    # Lyric state (from browser)
    highlighted_lyric: Optional[str]
    expected_lyric_time_ms: Optional[int]  # From LRC file
    lyric_line_number: Optional[int]

    # Screenshot
    screenshot_path: Optional[str]

    # Calculated drift
    drift_ms: Optional[int] = None  # highlighted lyric time - audio position


@dataclass
class SyncTestResult:
    """Overall test result."""
    test_start: str
    test_end: str
    track_name: str
    snapshots: List[SyncSnapshot]
    max_drift_ms: int
    avg_drift_ms: float
    drift_changes: List[Tuple[int, int]]  # (snapshot_idx, drift_change_ms)
    issues_detected: List[str]


def setup_logging(log_dir: Path) -> logging.Logger:
    """Set up logging to file and console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"sync_test_{timestamp}.log"

    logger = logging.getLogger("sync_test")
    logger.setLevel(logging.DEBUG)

    # File handler - detailed
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler - summary
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Logging to: {log_file}")
    return logger


def get_addon_position(logger: logging.Logger) -> dict:
    """Get current position from addon API."""
    try:
        resp = requests.get(f"{ADDON_URL}/api/position", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        logger.debug(f"Addon position: {data}")
        return data
    except Exception as e:
        logger.error(f"Failed to get addon position: {e}")
        return {"position_ms": 0, "state": "error", "track": None}


def start_playback(track_id: str, logger: logging.Logger) -> bool:
    """
    Start playback using Music Assistant service.

    Args:
        track_id: Spotify track ID (e.g. "spotify--RWrw92M3://track/57JVGBtBLCfHw2muk5416J")
        logger: Logger instance

    Returns:
        True if playback started successfully, False otherwise
    """
    if not HA_TOKEN:
        logger.error("HA_TOKEN not set, cannot start playback")
        return False

    try:
        logger.info(f"Starting playback on {PLAYER_ENTITY}")
        logger.info(f"Track ID: {track_id}")

        resp = requests.post(
            f"{HA_URL}/api/services/music_assistant/play_media",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            json={
                "entity_id": PLAYER_ENTITY,
                "media_id": track_id,
                "media_type": "track"
            },
            timeout=10
        )
        resp.raise_for_status()
        logger.info("Playback started successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to start playback: {e}")
        return False


def get_ha_player_state(logger: logging.Logger) -> dict:
    """Get current player state from Home Assistant."""
    if not HA_TOKEN:
        logger.warning("HA_TOKEN not set, skipping HA query")
        return {"media_position": 0, "state": "unknown", "media_title": None}

    try:
        resp = requests.get(
            f"{HA_URL}/api/states/{PLAYER_ENTITY}",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        attrs = data.get("attributes", {})
        logger.debug(f"HA state: state={data.get('state')}, position={attrs.get('media_position')}")
        return {
            "media_position": attrs.get("media_position", 0) or 0,
            "state": data.get("state", "unknown"),
            "media_title": attrs.get("media_title"),
            "media_artist": attrs.get("media_artist")
        }
    except Exception as e:
        logger.error(f"Failed to get HA state: {e}")
        return {"media_position": 0, "state": "error", "media_title": None}


def parse_lrc_file(track_name: str, logger: logging.Logger) -> dict:
    """Parse LRC file to get lyric timestamps. Returns {lyric_text: time_ms}."""
    lrc_mapping = {}

    # Try to find matching LRC file
    if not LRC_DIR.exists():
        logger.warning(f"LRC directory not found: {LRC_DIR}")
        return lrc_mapping

    # Clean track name for filename matching
    clean_name = track_name.replace(" - ", "_-_").replace(" ", "_")

    for lrc_file in LRC_DIR.glob("*.lrc"):
        if clean_name.lower() in lrc_file.stem.lower():
            logger.info(f"Found LRC file: {lrc_file}")
            try:
                with open(lrc_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        # Parse [MM:SS.xx] or [MM:SS:xx] format
                        match = re.match(r'\[(\d+):(\d+)[.:](\d+)\](.*)', line.strip())
                        if match:
                            mins, secs, centis, text = match.groups()
                            time_ms = (int(mins) * 60 + int(secs)) * 1000 + int(centis) * 10
                            text = text.strip()
                            if text:
                                lrc_mapping[text] = {"time_ms": time_ms, "line": line_num}
                logger.debug(f"Parsed {len(lrc_mapping)} lyric lines from LRC")
            except Exception as e:
                logger.error(f"Failed to parse LRC file: {e}")
            break

    return lrc_mapping


def capture_screenshot_and_lyrics(page: Page, screenshot_dir: Path, logger: logging.Logger) -> Tuple[Optional[str], Optional[str]]:
    """
    Capture screenshot with timeline visible and extract highlighted lyric.
    Returns (screenshot_path, highlighted_lyric_text).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    screenshot_path = screenshot_dir / f"sync_{timestamp}.png"

    try:
        # First, make sure timeline is visible
        # The timeline/scrubber might be hidden - we need to show it
        page.evaluate("""
            // Show timeline if hidden
            const timeline = document.querySelector('.timeline-container, .scrubber, #timeline');
            if (timeline) {
                timeline.style.display = 'block';
                timeline.style.opacity = '1';
                timeline.style.visibility = 'visible';
            }

            // Also try showing via settings if needed
            const scrubberToggle = document.querySelector('[data-setting="showScrubber"]');
            if (scrubberToggle && !scrubberToggle.checked) {
                scrubberToggle.click();
            }
        """)

        # Small wait for UI to update
        time.sleep(0.1)

        # Take screenshot
        page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info(f"Screenshot saved: {screenshot_path.name}")

        # Extract highlighted lyric
        highlighted = page.evaluate("""
            () => {
                // Look for highlighted/current lyric line
                // Common patterns: .current, .active, .highlighted, bold styling
                const selectors = [
                    '.lyric-line.current',
                    '.lyric-line.active',
                    '.lyric.current',
                    '.current-lyric',
                    '.highlighted',
                    '[data-current="true"]'
                ];

                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) return el.textContent.trim();
                }

                // Fallback: look for lyric with specific styling (larger/bold)
                const lyrics = document.querySelectorAll('.lyric-line, .lyric');
                for (const lyric of lyrics) {
                    const style = window.getComputedStyle(lyric);
                    if (style.fontWeight >= 700 || style.transform.includes('scale')) {
                        return lyric.textContent.trim();
                    }
                }

                return null;
            }
        """)

        logger.debug(f"Highlighted lyric: {highlighted}")
        return str(screenshot_path), highlighted

    except Exception as e:
        logger.error(f"Screenshot/lyric capture failed: {e}")
        return None, None


def take_sync_snapshot(
    page: Optional[Page],
    screenshot_dir: Path,
    lrc_mapping: dict,
    logger: logging.Logger
) -> SyncSnapshot:
    """Capture a complete sync snapshot."""
    now = datetime.now()
    timestamp = now.isoformat()
    timestamp_ms = int(now.timestamp() * 1000)

    # Get audio positions
    addon_data = get_addon_position(logger)
    ha_data = get_ha_player_state(logger)

    # Capture screenshot and highlighted lyric
    screenshot_path = None
    highlighted_lyric = None
    expected_time_ms = None
    lyric_line_num = None

    if page:
        screenshot_path, highlighted_lyric = capture_screenshot_and_lyrics(
            page, screenshot_dir, logger
        )

        # Look up expected time from LRC
        if highlighted_lyric and lrc_mapping:
            for lyric_text, info in lrc_mapping.items():
                # Fuzzy match - highlighted might be partial
                if lyric_text in highlighted_lyric or highlighted_lyric in lyric_text:
                    expected_time_ms = info["time_ms"]
                    lyric_line_num = info["line"]
                    break

    # Calculate drift if we have both audio position and expected lyric time
    drift_ms = None
    if expected_time_ms is not None:
        drift_ms = expected_time_ms - addon_data.get("position_ms", 0)

    snapshot = SyncSnapshot(
        timestamp=timestamp,
        timestamp_ms=timestamp_ms,
        addon_position_ms=addon_data.get("position_ms", 0),
        addon_state=addon_data.get("state", "unknown"),
        addon_track=addon_data.get("track"),
        ha_position_sec=ha_data.get("media_position", 0),
        ha_state=ha_data.get("state", "unknown"),
        ha_track=ha_data.get("media_title"),
        highlighted_lyric=highlighted_lyric,
        expected_lyric_time_ms=expected_time_ms,
        lyric_line_number=lyric_line_num,
        screenshot_path=screenshot_path,
        drift_ms=drift_ms
    )

    logger.info(
        f"Snapshot: audio={addon_data.get('position_ms', 0)}ms, "
        f"lyric_expected={expected_time_ms}ms, drift={drift_ms}ms"
    )

    return snapshot


def analyze_results(snapshots: List[SyncSnapshot], logger: logging.Logger) -> SyncTestResult:
    """Analyze sync snapshots to detect issues."""
    issues = []
    drift_changes = []
    drifts = [s.drift_ms for s in snapshots if s.drift_ms is not None]

    if not drifts:
        logger.warning("No drift measurements available")
        max_drift = 0
        avg_drift = 0.0
    else:
        max_drift = max(abs(d) for d in drifts)
        avg_drift = sum(abs(d) for d in drifts) / len(drifts)

        # Check for drift changes between snapshots
        prev_drift = None
        for i, s in enumerate(snapshots):
            if s.drift_ms is not None:
                if prev_drift is not None:
                    change = abs(s.drift_ms - prev_drift)
                    if change > 500:  # More than 500ms change
                        drift_changes.append((i, change))
                        issues.append(f"Snapshot {i}: Drift jumped by {change}ms")
                prev_drift = s.drift_ms

        # Check thresholds
        if max_drift > 2000:
            issues.append(f"Max drift exceeds 2 seconds: {max_drift}ms")
        if avg_drift > 1000:
            issues.append(f"Average drift exceeds 1 second: {avg_drift:.0f}ms")

    # Check for state changes
    states = [s.addon_state for s in snapshots]
    if "playing" in states and states.count("playing") < len(states):
        issues.append("Playback state changed during test")

    track_name = snapshots[0].addon_track if snapshots else "Unknown"

    return SyncTestResult(
        test_start=snapshots[0].timestamp if snapshots else "",
        test_end=snapshots[-1].timestamp if snapshots else "",
        track_name=track_name or "Unknown",
        snapshots=snapshots,
        max_drift_ms=max_drift,
        avg_drift_ms=avg_drift,
        drift_changes=drift_changes,
        issues_detected=issues
    )


def run_sync_test(
    num_checks: int = 5,
    interval_seconds: int = 10,
    auto_play: bool = False,
    track_id: str = None,
    logger: logging.Logger = None
) -> SyncTestResult:
    """Run the full sync verification test."""

    if logger is None:
        logger = setup_logging(LOG_DIR)

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("LYRIC SCROLL SYNC VERIFICATION TEST")
    logger.info("=" * 60)
    logger.info(f"Checks: {num_checks}, Interval: {interval_seconds}s")
    logger.info(f"Addon URL: {ADDON_URL}")
    logger.info(f"HA Player: {PLAYER_ENTITY}")
    if auto_play:
        logger.info(f"Auto-play: Enabled (track: {track_id or DEFAULT_TRACK})")
    logger.info("")

    snapshots = []
    page = None
    browser = None
    playwright_ctx = None
    lrc_mapping = {}

    try:
        # Start playback if requested
        if auto_play:
            track_to_play = track_id or DEFAULT_TRACK
            if start_playback(track_to_play, logger):
                logger.info("Waiting 5 seconds for playback to start...")
                time.sleep(5)
            else:
                logger.error("Failed to start playback, continuing anyway...")

        # Initial check - is music playing?
        initial = get_addon_position(logger)
        if initial.get("state") != "playing":
            logger.warning(f"Player state is '{initial.get('state')}', not 'playing'")
            logger.warning("Test may not be accurate if music is not playing")

        track = initial.get("track", "Unknown")
        logger.info(f"Track: {track}")

        # Load LRC mapping
        if track:
            lrc_mapping = parse_lrc_file(track, logger)

        # Set up browser if playwright available
        if HAS_PLAYWRIGHT:
            logger.info("Starting browser...")
            playwright_ctx = sync_playwright().start()
            browser = playwright_ctx.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})

            # Navigate to addon
            logger.info(f"Loading {ADDON_URL}...")
            page.goto(ADDON_URL, wait_until="networkidle")
            time.sleep(2)  # Wait for lyrics to load

        # Take snapshots
        for i in range(num_checks):
            logger.info(f"\n--- Snapshot {i+1}/{num_checks} ---")
            snapshot = take_sync_snapshot(page, SCREENSHOT_DIR, lrc_mapping, logger)
            snapshots.append(snapshot)

            if i < num_checks - 1:
                logger.info(f"Waiting {interval_seconds}s...")
                time.sleep(interval_seconds)

    finally:
        if page:
            page.close()
        if browser:
            browser.close()
        if playwright_ctx:
            playwright_ctx.stop()

    # Analyze results
    logger.info("\n" + "=" * 60)
    logger.info("ANALYSIS")
    logger.info("=" * 60)

    result = analyze_results(snapshots, logger)

    logger.info(f"Track: {result.track_name}")
    logger.info(f"Max drift: {result.max_drift_ms}ms")
    logger.info(f"Avg drift: {result.avg_drift_ms:.0f}ms")

    if result.issues_detected:
        logger.warning("Issues detected:")
        for issue in result.issues_detected:
            logger.warning(f"  - {issue}")
    else:
        logger.info("No sync issues detected!")

    # Save detailed results
    results_file = LOG_DIR / f"sync_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, "w") as f:
        json.dump({
            "test_start": result.test_start,
            "test_end": result.test_end,
            "track_name": result.track_name,
            "max_drift_ms": result.max_drift_ms,
            "avg_drift_ms": result.avg_drift_ms,
            "issues": result.issues_detected,
            "snapshots": [asdict(s) for s in result.snapshots]
        }, f, indent=2)
    logger.info(f"\nDetailed results saved to: {results_file}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Lyric Scroll Sync Verification Test")
    parser.add_argument("--checks", type=int, default=5, help="Number of sync checks (default: 5)")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between checks (default: 10)")
    parser.add_argument("--play", action="store_true", help="Start playback before testing")
    parser.add_argument("--track", type=str, help="Spotify track ID to play (default: Queen - Another One Bites The Dust)")
    args = parser.parse_args()

    logger = setup_logging(LOG_DIR)

    try:
        result = run_sync_test(
            num_checks=args.checks,
            interval_seconds=args.interval,
            auto_play=args.play,
            track_id=args.track,
            logger=logger
        )

        # Exit code based on issues
        if result.issues_detected:
            sys.exit(1)
        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
