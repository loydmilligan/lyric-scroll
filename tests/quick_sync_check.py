#!/usr/bin/env python3
"""
Quick Sync Check - API only, no browser required.

Rapidly polls the addon position API and logs changes to detect:
- Position jumps (lyrics restarting)
- Position stuttering (position goes backwards briefly)
- Position gaps (large jumps forward)

Usage:
    python3 quick_sync_check.py [--duration SECONDS] [--interval MS]

Output:
    Prints anomalies to console and logs to tests/logs/
"""

import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


ADDON_URL = "https://lyric-scroll.mattmariani.com"
LOG_DIR = Path(__file__).parent / "logs"


def get_position() -> dict:
    """Get current position from addon."""
    try:
        resp = requests.get(f"{ADDON_URL}/api/position", timeout=2)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"position_ms": -1, "state": "error", "track": None, "error": str(e)}


def run_check(duration_sec: int = 60, interval_ms: int = 200):
    """Run continuous sync check."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"quick_sync_{timestamp}.log"

    print(f"Quick Sync Check - {duration_sec}s duration, {interval_ms}ms interval")
    print(f"Logging to: {log_file}")
    print()

    with open(log_file, "w") as f:
        f.write(f"Quick Sync Check started at {datetime.now().isoformat()}\n")
        f.write(f"Duration: {duration_sec}s, Interval: {interval_ms}ms\n")
        f.write("-" * 60 + "\n")

        start_time = time.time()
        end_time = start_time + duration_sec

        prev_position = None
        prev_time = None
        prev_track = None

        anomaly_count = 0
        sample_count = 0

        # Expected position change per interval (with some tolerance)
        expected_change_min = interval_ms * 0.5  # Allow 50% slower
        expected_change_max = interval_ms * 2.0  # Allow 2x faster

        while time.time() < end_time:
            now = datetime.now()
            now_ms = time.time() * 1000

            data = get_position()
            pos = data.get("position_ms", -1)
            state = data.get("state", "unknown")
            track = data.get("track")

            sample_count += 1

            # Log every sample
            log_line = f"{now.strftime('%H:%M:%S.%f')[:-3]} | pos={pos:>8}ms | state={state:>8} | track={track}"

            if prev_position is not None and state == "playing":
                elapsed_ms = now_ms - prev_time
                pos_change = pos - prev_position

                anomaly = None

                # Check for track change
                if track != prev_track and prev_track is not None:
                    anomaly = f"TRACK_CHANGE: {prev_track} -> {track}"

                # Check for position jump backwards (restart/stutter)
                elif pos_change < -500:  # More than 500ms backwards
                    anomaly = f"JUMP_BACK: {prev_position}ms -> {pos}ms (change: {pos_change}ms)"

                # Check for large forward jump (skip)
                elif pos_change > elapsed_ms * 3:  # More than 3x expected
                    anomaly = f"JUMP_FORWARD: {prev_position}ms -> {pos}ms (change: {pos_change}ms, expected ~{elapsed_ms:.0f}ms)"

                # Check for stall (position didn't change when it should have)
                elif pos_change < elapsed_ms * 0.3 and elapsed_ms > 300:  # Less than 30% of expected change
                    anomaly = f"STALL: {prev_position}ms -> {pos}ms (change: {pos_change}ms over {elapsed_ms:.0f}ms)"

                if anomaly:
                    anomaly_count += 1
                    log_line += f" | *** {anomaly} ***"
                    print(f"[{now.strftime('%H:%M:%S')}] {anomaly}")

            f.write(log_line + "\n")
            f.flush()

            prev_position = pos
            prev_time = now_ms
            prev_track = track

            # Sleep for interval
            time.sleep(interval_ms / 1000)

        # Summary
        elapsed = time.time() - start_time
        summary = f"""
{"=" * 60}
SUMMARY
{"=" * 60}
Duration: {elapsed:.1f}s
Samples: {sample_count}
Anomalies: {anomaly_count}
Anomaly rate: {anomaly_count / sample_count * 100:.1f}%
"""
        f.write(summary)
        print(summary)

        if anomaly_count == 0:
            print("No sync anomalies detected!")
        else:
            print(f"Found {anomaly_count} anomalies - check {log_file} for details")


def main():
    parser = argparse.ArgumentParser(description="Quick Sync Check")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (default: 60)")
    parser.add_argument("--interval", type=int, default=200, help="Poll interval in ms (default: 200)")
    args = parser.parse_args()

    try:
        run_check(duration_sec=args.duration, interval_ms=args.interval)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
