#!/usr/bin/env python3
"""MQTT-based agent sync for GCA.

Usage:
    ./mqtt-sync.py send [file]    Send message(s) from outbox
    ./mqtt-sync.py receive        Receive messages to inbox
    ./mqtt-sync.py status         Check connection status
"""

import json
import os
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

# Paths
SCRIPT_DIR = Path(__file__).parent
OUTBOX = SCRIPT_DIR / "outbox"
INBOX = SCRIPT_DIR / "inbox"
ARCHIVE = SCRIPT_DIR / "archive"

# Load config from .env
def load_env():
    env_file = SCRIPT_DIR / ".env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config

ENV = load_env()
BROKER = ENV.get("MQTT_BROKER", "192.168.4.158")
PORT = int(ENV.get("MQTT_PORT", "1883"))
USER = ENV.get("MQTT_USER", "gca")
PASS = ENV.get("MQTT_PASS", "")

# Topics (base paths - messages use subtopics per message ID)
SEND_TOPIC_BASE = "agent-sync/gca-to-major-tom"
RECV_TOPIC_BASE = "agent-sync/major-tom-to-gca"
STATUS_TOPIC = "agent-sync/gca/status"


def get_client():
    """Create and connect MQTT client."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gca-sync", protocol=mqtt.MQTTv311)
    client.username_pw_set(USER, PASS)
    client.connect(BROKER, PORT, keepalive=60)
    return client


def send_message(filepath: Path):
    """Send a single message file."""
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return False

    content = filepath.read_text()
    filename = filepath.name

    # Use unique topic per message so retain doesn't overwrite
    msg_id = filepath.stem  # e.g., "2026-03-15-001-gca-to-major-tom"
    topic = f"{SEND_TOPIC_BASE}/{msg_id}"

    payload = json.dumps({
        "filename": filename,
        "content": content,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    client = get_client()
    client.loop_start()
    result = client.publish(topic, payload, retain=True, qos=1)
    result.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()

    print(f"Sent: {filename} -> {topic}")

    # Move to archive
    dest = ARCHIVE / filename
    filepath.rename(dest)
    print(f"Archived: {filename}")

    return True


def send_all():
    """Send all messages in outbox."""
    files = list(OUTBOX.glob("*.md"))
    if not files:
        print("Outbox is empty.")
        return

    for f in sorted(files):
        send_message(f)

    print(f"Sent {len(files)} message(s).")


def receive_messages():
    """Receive messages from Major Tom."""
    # Subscribe to wildcard to get all message subtopics
    recv_pattern = f"{RECV_TOPIC_BASE}/+"
    print(f"Checking: {recv_pattern}")

    received = []

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            filename = payload.get("filename", f"msg-{int(time.time())}.md")
            content = payload.get("content", msg.payload.decode())

            dest = INBOX / filename
            archived = ARCHIVE / filename
            # Check both inbox and archive to avoid re-downloading
            if not dest.exists() and not archived.exists():
                dest.write_text(content)
                print(f"Received: {filename}")
                received.append(filename)
            else:
                print(f"Already have: {filename}")
        except json.JSONDecodeError:
            # Raw message, not JSON
            filename = f"raw-{int(time.time())}.md"
            dest = INBOX / filename
            dest.write_text(msg.payload.decode())
            print(f"Received raw: {filename}")
            received.append(filename)

    client = get_client()
    client.on_message = on_message
    client.subscribe(recv_pattern)

    # Wait briefly for retained messages
    client.loop_start()
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    if not received:
        print("No new messages.")


def check_status():
    """Test MQTT connection."""
    print(f"Connecting to {BROKER}:{PORT} as {USER}...")

    try:
        client = get_client()
        client.loop_start()
        status_msg = f"GCA online {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        result = client.publish(STATUS_TOPIC, status_msg, retain=True)
        result.wait_for_publish(timeout=5)
        client.loop_stop()
        client.disconnect()
        print("Connection OK")
        print(f"Published: {status_msg}")
    except Exception as e:
        print(f"Connection FAILED: {e}")
        sys.exit(1)


def main():
    INBOX.mkdir(exist_ok=True)
    OUTBOX.mkdir(exist_ok=True)
    ARCHIVE.mkdir(exist_ok=True)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "send":
        if len(sys.argv) > 2:
            send_message(Path(sys.argv[2]))
        else:
            send_all()
    elif cmd == "receive":
        receive_messages()
    elif cmd == "status":
        check_status()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
